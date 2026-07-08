"""The minimal transport interface shared by the NATS client and the fake.

Kept dependency-free (no ``nats`` import) so the rest of the package can be
imported without ``nats-py`` installed; only ``serve``/``agent`` need the real
client.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

# A responder handler: receives the decoded request dict, returns the reply dict.
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@runtime_checkable
class Transport(Protocol):
    """Bidirectional request/reply + publish over some relay.

    Payloads are plain JSON-serializable dicts; encoding is the transport's job.
    """

    async def request(self, subject: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Send a request and await the reply dict (requester side)."""
        ...

    async def subscribe(self, subject: str, queue: str | None, handler: Handler) -> None:
        """Register a responder for *subject* (responder side).

        The transport must always send *some* reply — if ``handler`` raises, it
        replies with an ``{"ok": False, "error": ...}`` envelope so requesters
        never hang.
        """
        ...

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget publish (e.g. progress events)."""
        ...

    async def close(self) -> None:
        """Tear down the connection."""
        ...
