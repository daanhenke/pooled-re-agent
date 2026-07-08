"""Thin async NATS client implementing :class:`Transport`.

``nats-py`` is imported lazily so importing this module (and the rest of the
package) does not require it — only ``re-agent serve`` / ``re-agent agent``
actually open a connection.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from re_agent.config.schema import TransportConfig
from re_agent.transport.base import Handler

logger = logging.getLogger(__name__)


class NatsTransport:
    """Wraps a NATS connection with JSON request/reply + publish."""

    def __init__(self, nc: Any, request_timeout_s: float) -> None:
        self._nc = nc
        self._request_timeout_s = request_timeout_s

    @classmethod
    async def connect(cls, config: TransportConfig, *, name: str = "re-agent") -> NatsTransport:
        """Open a NATS connection from a :class:`TransportConfig`.

        Auth precedence: creds file > token > user/password > anonymous.
        """
        try:
            import nats
        except ImportError as err:
            raise ImportError(
                "nats-py is required for the orchestrator server and pooled agents. "
                "Install it with: pip install 'nats-py>=2.6'  (or: pip install 're-agent[agent]')"
            ) from err

        opts: dict[str, Any] = {
            "servers": list(config.servers),
            "name": name,
            "connect_timeout": config.connect_timeout_s,
            "max_reconnect_attempts": -1,  # keep retrying; pools come and go
        }
        if config.creds_file:
            opts["user_credentials"] = config.creds_file
        elif config.token:
            opts["token"] = config.token
        elif config.user is not None:
            opts["user"] = config.user
            opts["password"] = config.password or ""

        if config.tls:
            import ssl

            ctx = ssl.create_default_context()
            if config.tls_ca_file:
                ctx.load_verify_locations(config.tls_ca_file)
            opts["tls"] = ctx

        nc = await nats.connect(**opts)
        logger.info("Connected to NATS at %s (project=%s)", config.servers, config.project)
        return cls(nc, float(config.request_timeout_s))

    async def request(self, subject: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        msg = await self._nc.request(subject, data, timeout=timeout or self._request_timeout_s)
        reply: dict[str, Any] = json.loads(msg.data)
        return reply

    async def subscribe(self, subject: str, queue: str | None, handler: Handler) -> None:
        async def _cb(msg: Any) -> None:
            reply: dict[str, Any]
            try:
                req = json.loads(msg.data)
                reply = await handler(req)
            except Exception as exc:  # never let a requester hang
                logger.exception("Handler error on %s", subject)
                reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            if msg.reply:
                await self._nc.publish(msg.reply, json.dumps(reply).encode("utf-8"))

        await self._nc.subscribe(subject, queue=queue or "", cb=_cb)
        logger.info("Subscribed to %s (queue=%s)", subject, queue or "")

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        await self._nc.publish(subject, json.dumps(payload).encode("utf-8"))

    async def close(self) -> None:
        await self._nc.drain()
