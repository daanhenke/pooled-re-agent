"""JSON-backed persistent session state for tracking reversal progress."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from re_agent.core.models import FunctionTarget, ReversalResult
from re_agent.utils.address import normalize_address


class Session:
    """Tracks reversal progress in a JSON file.

    When serving pooled agents, ``in_progress`` also holds short-lived *leases*
    on functions that have been handed out but not yet completed, so two agents
    are never given the same function.  An expired lease (agent crashed / went
    away) is simply ignored, which re-offers the function.
    """

    def __init__(self, path: str | Path = "re-agent-progress.json") -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {"functions": {}, "runs": [], "in_progress": {}, "queue": []}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._data = {"functions": {}, "runs": [], "in_progress": {}, "queue": []}
        # Tolerate older files that predate leasing/queueing.
        self._data.setdefault("functions", {})
        self._data.setdefault("runs", [])
        self._data.setdefault("in_progress", {})
        self._data.setdefault("queue", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        # os.replace is an atomic overwrite on all platforms; Path.rename raises
        # FileExistsError on Windows when the destination already exists.
        os.replace(tmp, self.path)

    def record_result(self, result: ReversalResult) -> None:
        addr = normalize_address(result.target.address)
        entry = {
            "address": result.target.address,
            "class_name": result.target.class_name,
            "function_name": result.target.function_name,
            "success": result.success,
            "rounds_used": result.rounds_used,
            "verdict": result.checker_verdict.verdict.value if result.checker_verdict else None,
            "parity_status": result.parity_status.value if result.parity_status else None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._data["functions"][addr] = entry
        self._data["runs"].append(entry)
        self._data["in_progress"].pop(addr, None)  # completing releases any lease
        self.save()

    # -- leasing (pooled-agent job assignment) --------------------------------

    def mark_in_progress(self, target: FunctionTarget, agent_id: str, lease_s: int) -> None:
        """Lease a function to an agent for ``lease_s`` seconds."""
        addr = normalize_address(target.address)
        self._data["in_progress"][addr] = {
            "address": target.address,
            "class_name": target.class_name,
            "function_name": target.function_name,
            "caller_count": target.caller_count,
            "agent_id": agent_id,
            "expiry": time.time() + lease_s,
        }
        self.save()

    def release(self, address: str) -> None:
        """Drop a lease (e.g. the agent failed the job) so it can be re-offered."""
        addr = normalize_address(address)
        if self._data["in_progress"].pop(addr, None) is not None:
            self.save()

    def active_in_progress(self) -> set[str]:
        """Return normalized addresses with a *live* (unexpired) lease.

        Expired leases are pruned as a side effect so abandoned jobs return to
        the pool automatically.
        """
        now = time.time()
        live: set[str] = set()
        expired: list[str] = []
        for addr, info in self._data["in_progress"].items():
            if info.get("expiry", 0) > now:
                live.add(addr)
            else:
                expired.append(addr)
        if expired:
            for addr in expired:
                self._data["in_progress"].pop(addr, None)
            self.save()
        return live

    def is_in_progress(self, address: str) -> bool:
        """Return True if this address currently holds a live lease."""
        return normalize_address(address) in self.active_in_progress()

    # -- explicit work queue (re-agent enqueue) -------------------------------

    def enqueue_targets(self, targets: list[FunctionTarget]) -> int:
        """Append targets to the priority queue; skip dupes and done functions.

        The queue is a persistent *priority list*: assignment drains it before
        the greedy picker.  Entries are not removed on assignment — leasing and
        the attempted-filter exclude them, and completed entries are pruned, so
        an abandoned (lease-expired) job reappears at the front automatically.

        Returns the number of newly-queued targets.
        """
        self._prune_queue()
        existing = {normalize_address(e["address"]) for e in self._data["queue"]}
        added = 0
        for t in targets:
            addr = normalize_address(t.address)
            if addr in existing or self.is_attempted(t.address):
                continue
            self._data["queue"].append({
                "address": t.address,
                "class_name": t.class_name,
                "function_name": t.function_name,
                "caller_count": t.caller_count,
            })
            existing.add(addr)
            added += 1
        if added:
            self.save()
        return added

    def queued_targets(self) -> list[FunctionTarget]:
        """Return the queued targets in priority (FIFO) order, pruning done ones."""
        self._prune_queue()
        return [
            FunctionTarget(
                address=e["address"],
                class_name=e.get("class_name", ""),
                function_name=e.get("function_name", ""),
                caller_count=e.get("caller_count", 0),
            )
            for e in self._data["queue"]
        ]

    def queue_size(self) -> int:
        self._prune_queue()
        return len(self._data["queue"])

    def _prune_queue(self) -> None:
        """Drop queue entries that have since been attempted (completed/failed)."""
        kept = [e for e in self._data["queue"] if not self.is_attempted(e["address"])]
        if len(kept) != len(self._data["queue"]):
            self._data["queue"] = kept
            self.save()

    def is_completed(self, address: str) -> bool:
        addr = normalize_address(address)
        func = self._data["functions"].get(addr)
        return func is not None and func.get("success", False)

    def is_attempted(self, address: str) -> bool:
        """Return True if this address has been attempted (pass or fail)."""
        addr = normalize_address(address)
        return addr in self._data["functions"]

    def get_class_summary(self, class_name: str) -> dict[str, int]:
        total = 0
        passed = 0
        failed = 0
        for func in self._data["functions"].values():
            if func.get("class_name") == class_name:
                total += 1
                if func.get("success"):
                    passed += 1
                else:
                    failed += 1
        return {"total": total, "passed": passed, "failed": failed}

    def get_summary(self) -> dict[str, Any]:
        funcs = self._data["functions"]
        total = len(funcs)
        passed = sum(1 for f in funcs.values() if f.get("success"))
        failed = total - passed
        classes: set[str] = set()
        for f in funcs.values():
            cn = f.get("class_name", "")
            if cn:
                classes.add(cn)
        return {
            "total_functions": total,
            "passed": passed,
            "failed": failed,
            "classes_touched": len(classes),
        }

    def get_all_functions(self) -> list[dict[str, Any]]:
        return list(self._data["functions"].values())
