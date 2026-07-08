"""The orchestrator NATS service: proxy RE tool calls, assign + finalize jobs.

Three responders (all agent-initiated request/reply):

- ``rpc``          — run one RE tool call against the real backend / source tree
- ``job.request``  — lease the next function to an agent
- ``job.submit``   — finalize a returned result (parity + session), or release
                     the lease on a reported failure

Backend access is serialized behind one lock because the Ghidra CLI is a single
subprocess; session/job state is serialized behind another.  Blocking work runs
in the default executor so the event loop stays responsive.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from re_agent.config.schema import ReAgentConfig
from re_agent.core.function_picker import pick_next, pick_next_global
from re_agent.core.models import FunctionTarget, ReversalResult
from re_agent.core.session import Session
from re_agent.orchestrator.single import finalize_result
from re_agent.transport import protocol as proto
from re_agent.transport import wire
from re_agent.transport.base import Transport
from re_agent.utils.address import normalize_address

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Responds to agent RPCs against a real backend, source tree, and session."""

    def __init__(
        self,
        config: ReAgentConfig,
        backend: Any,          # REBackend (real GhidraBridgeBackend)
        session: Session,
        indexer: Any = None,   # SourceIndexer | None
        source_ctx: Any = None,  # SourceContextBuilder | None (has .build(target))
    ) -> None:
        self.config = config
        self.backend = backend
        self.session = session
        self.indexer = indexer
        self.source_ctx = source_ctx
        self._backend_lock = asyncio.Lock()  # serialize the single Ghidra CLI
        self._state_lock = asyncio.Lock()    # serialize session + job assignment

    # -- RPC (proxied RE tool calls) -----------------------------------------

    async def handle_rpc(self, req: dict[str, Any]) -> dict[str, Any]:
        op = req.get("op", "")
        args = req.get("args", {}) or {}
        loop = asyncio.get_running_loop()
        try:
            async with self._backend_lock:
                result = await loop.run_in_executor(None, self._dispatch, op, args)
            return {"ok": True, "result": result}
        except Exception as exc:
            logger.exception("rpc op %r failed", op)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _dispatch(self, op: str, args: dict[str, Any]) -> Any:
        build_ctx = self.source_ctx.build if self.source_ctx is not None else None
        return proto.dispatch(self.backend, build_ctx, op, args)

    # -- job assignment -------------------------------------------------------

    async def handle_job_request(self, req: dict[str, Any]) -> dict[str, Any]:
        agent_id = req.get("agent_id", "?")
        loop = asyncio.get_running_loop()
        async with self._state_lock:
            async with self._backend_lock:
                target = await loop.run_in_executor(None, self._pick_target)
            if target is None:
                return {"target": None}
            self.session.mark_in_progress(target, agent_id, self.config.orchestrator.job_lease_s)
        logger.info("Assigned %s::%s (%s) to %s",
                    target.class_name, target.function_name, target.address, agent_id)
        return {"target": wire.encode_target(target), "config": self._job_config()}

    def _pick_target(self) -> FunctionTarget | None:
        # 1. Explicit queue (re-agent enqueue) has priority over the greedy picker.
        leased = self.session.active_in_progress()
        for qt in self.session.queued_targets():
            if not self.session.is_attempted(qt.address) and normalize_address(qt.address) not in leased:
                return qt
        # 2. Fallback picker — disabled when auto_pick is off (queue-only mode).
        if not self.config.orchestrator.auto_pick:
            return None
        classes = self.config.orchestrator.classes
        if classes:
            for cls in classes:
                t = pick_next(cls, self.backend, self.session)
                if t is not None:
                    return t
            return None
        return pick_next_global(self.backend, self.session)

    # -- enqueue (explicit work list) -----------------------------------------

    async def handle_enqueue(self, req: dict[str, Any]) -> dict[str, Any]:
        addresses = req.get("addresses", []) or []
        filt = req.get("filter")
        loop = asyncio.get_running_loop()
        try:
            async with self._backend_lock:
                targets = await loop.run_in_executor(None, self._resolve_enqueue, addresses, filt)
        except Exception as exc:
            logger.exception("enqueue resolve failed")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        async with self._state_lock:
            added = self.session.enqueue_targets(targets)
            size = self.session.queue_size()
        logger.info("Enqueued %d target(s) of %d resolved; queue size now %d", added, len(targets), size)
        return {"ok": True, "enqueued": added, "resolved": len(targets), "queue_size": size}

    def _resolve_enqueue(self, addresses: list[str], filt: str | None) -> list[FunctionTarget]:
        """Resolve addresses/filter into FunctionTargets (backend name lookup)."""
        targets: list[FunctionTarget] = []
        for addr in addresses:
            class_name, function_name = "", ""
            try:
                name = self.backend.decompile(addr).name or ""
                if "::" in name:
                    class_name, _, function_name = name.rpartition("::")
                else:
                    function_name = name
            except Exception:
                logger.debug("enqueue: could not resolve name for %s", addr, exc_info=True)
            targets.append(FunctionTarget(address=addr, class_name=class_name, function_name=function_name))
        if filt:
            try:
                for fe in self.backend.unimplemented(filt):
                    targets.append(FunctionTarget(
                        address=fe.address, class_name=fe.class_name,
                        function_name=fe.name, caller_count=fe.caller_count,
                    ))
            except Exception:
                logger.debug("enqueue: unimplemented(%r) failed", filt, exc_info=True)
        return targets

    def _job_config(self) -> dict[str, Any]:
        o = self.config.orchestrator
        return {
            "max_rounds": o.max_review_rounds,
            "objective_verifier_enabled": o.objective_verifier_enabled,
            "objective_call_count_tolerance": o.objective_call_count_tolerance,
            "objective_control_flow_tolerance": o.objective_control_flow_tolerance,
        }

    # -- job submission -------------------------------------------------------

    async def handle_job_submit(self, req: dict[str, Any]) -> dict[str, Any]:
        error = req.get("error")
        if error:
            address = req.get("address", "")
            async with self._state_lock:
                self.session.release(address)
            logger.warning("Agent %s failed %s: %s — lease released",
                           req.get("agent_id", "?"), address, error)
            return {"ok": True, "released": True}

        result_d = req.get("result")
        if not result_d:
            return {"ok": False, "error": "submission had neither 'result' nor 'error'"}

        result = wire.decode_reversal_result(result_d)
        loop = asyncio.get_running_loop()
        async with self._state_lock, self._backend_lock:
            finalized = await loop.run_in_executor(None, self._finalize, result)
        logger.info("Recorded %s from %s: success=%s parity=%s",
                    result.target.address, req.get("agent_id", "?"),
                    finalized.success, finalized.parity_status.value if finalized.parity_status else None)
        return {
            "ok": True,
            "success": finalized.success,
            "parity_status": finalized.parity_status.value if finalized.parity_status else None,
        }

    def _finalize(self, result: ReversalResult) -> ReversalResult:
        return finalize_result(
            result,
            self.config,
            self.backend,
            session=self.session,
            indexer=self.indexer,
        )

    # -- wiring ---------------------------------------------------------------

    async def subscribe(self, transport: Transport) -> None:
        """Register all three responders on the transport (no blocking wait)."""
        project = self.config.transport.project
        await transport.subscribe(proto.rpc_subject(project), proto.ORCH_QUEUE, self.handle_rpc)
        await transport.subscribe(proto.job_request_subject(project), proto.ORCH_QUEUE, self.handle_job_request)
        await transport.subscribe(proto.job_submit_subject(project), proto.ORCH_QUEUE, self.handle_job_submit)
        await transport.subscribe(proto.enqueue_subject(project), proto.ORCH_QUEUE, self.handle_enqueue)

    async def serve(self, transport: Transport) -> None:
        """Subscribe all three responders and run until cancelled."""
        await self.subscribe(transport)
        project = self.config.transport.project
        logger.info("Orchestrator serving project %r", project)
        print(f"Orchestrator online — project '{project}', serving on {self.config.transport.servers}")
        await asyncio.Event().wait()  # serve forever
