"""In-process transport that wires requesters straight to responders.

Used by tests and by anything that wants to run the orchestrator service and an
agent worker in one process without a NATS broker.  Requests are JSON round-
tripped (so serialization bugs surface just like over the wire) and dispatched
to the handler registered for the subject; queue groups are ignored (a single
responder).
"""
from __future__ import annotations

import json
from typing import Any

from re_agent.transport.base import Handler


class FakeTransport:
    """A shared message bus. Give the same instance to server and worker."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def request(self, subject: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        handler = self._handlers.get(subject)
        if handler is None:
            raise RuntimeError(f"No responder registered for subject {subject!r}")
        req = json.loads(json.dumps(payload))  # emulate wire round-trip
        try:
            reply = await handler(req)
        except Exception as exc:
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        out: dict[str, Any] = json.loads(json.dumps(reply))
        return out

    async def subscribe(self, subject: str, queue: str | None, handler: Handler) -> None:
        self._handlers[subject] = handler

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self.published.append((subject, json.loads(json.dumps(payload))))

    async def close(self) -> None:  # nothing to tear down
        return None
