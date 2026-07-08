"""A backend that proxies every RE tool call to the orchestrator over NATS.

:class:`RemoteBackend` implements :class:`re_agent.backend.protocol.REBackend`,
so it drops straight into the existing reverser/checker/objective loop — the
loop cannot tell it apart from a local Ghidra backend.  Each call is one NATS
request/reply; results are memoized per instance (one instance per job) so the
repeated ``decompile`` calls made by the reverser, checker, and objective
verifier collapse to a single round-trip.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from re_agent.backend.protocol import BackendCapabilities
from re_agent.core.models import (
    AsmResult,
    DecompileResult,
    EnumDef,
    FunctionEntry,
    StructDef,
    XRef,
)
from re_agent.transport import protocol as proto

# A blocking request: given a subject and payload, return the reply dict.  The
# worker app supplies one that bridges this (worker-thread) call onto the async
# NATS connection running on the event loop.
BlockingRequest = Callable[[str, dict[str, Any]], dict[str, Any]]


class RpcClient:
    """Synchronous op-based RPC over the orchestrator's ``rpc`` subject."""

    def __init__(self, project: str, request: BlockingRequest) -> None:
        self._subject = proto.rpc_subject(project)
        self._request = request

    def call(self, op: str, args: dict[str, Any]) -> Any:
        """Send one RPC and return the raw (JSON-safe) result, or raise."""
        reply = self._request(self._subject, {"op": op, "args": args})
        if not reply.get("ok", False):
            raise RuntimeError(reply.get("error") or f"RPC {op!r} failed")
        return reply.get("result")


class RemoteBackend:
    """REBackend implementation whose data comes from the orchestrator."""

    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc
        self._cache: dict[str, Any] = {}

    def _op(self, op: str, args: dict[str, Any] | None = None) -> Any:
        args = args or {}
        key = op + ":" + json.dumps(args, sort_keys=True)
        if key in self._cache:
            return self._cache[key]
        result = proto.decode_rpc_result(op, self._rpc.call(op, args))
        self._cache[key] = result
        return result

    @property
    def capabilities(self) -> BackendCapabilities:
        caps: BackendCapabilities = self._op(proto.OP_CAPABILITIES)
        return caps

    def decompile(self, target: str) -> DecompileResult:
        result: DecompileResult = self._op(proto.OP_DECOMPILE, {"target": target})
        return result

    def xrefs_to(self, target: str) -> list[XRef]:
        result: list[XRef] = self._op(proto.OP_XREFS_TO, {"target": target})
        return result

    def xrefs_from(self, target: str) -> list[XRef]:
        result: list[XRef] = self._op(proto.OP_XREFS_FROM, {"target": target})
        return result

    def get_struct(self, name: str) -> StructDef | None:
        result: StructDef | None = self._op(proto.OP_GET_STRUCT, {"name": name})
        return result

    def get_enum(self, name: str) -> EnumDef | None:
        result: EnumDef | None = self._op(proto.OP_GET_ENUM, {"name": name})
        return result

    def get_asm(self, target: str) -> AsmResult | None:
        result: AsmResult | None = self._op(proto.OP_GET_ASM, {"target": target})
        return result

    def search(self, pattern: str) -> list[FunctionEntry]:
        result: list[FunctionEntry] = self._op(proto.OP_SEARCH, {"pattern": pattern})
        return result

    def unimplemented(self, filter_pattern: str | None = None) -> list[FunctionEntry]:
        result: list[FunctionEntry] = self._op(proto.OP_UNIMPLEMENTED, {"filter_pattern": filter_pattern})
        return result

    def remaining(self, class_name: str | None = None) -> list[FunctionEntry]:
        result: list[FunctionEntry] = self._op(proto.OP_REMAINING, {"class_name": class_name})
        return result
