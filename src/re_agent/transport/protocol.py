"""NATS subjects, RPC op names, and the shared request/reply shapes.

Message flow (all agent-initiated request/reply):

- ``re.<project>.rpc``          {op, args}          -> {ok, result, error}
- ``re.<project>.job.request``  {agent_id, model}   -> {target|null, config}
- ``re.<project>.job.submit``   {result, agent_id}  -> {ok, parity_status, error}
- ``re.<project>.events``       {kind, ...}         (fire-and-forget publish)

The ``rpc`` subject proxies the RE "tool calls": every method of
:class:`re_agent.backend.protocol.REBackend` plus ``source_context``.  The
op->result encode/decode mapping lives here (used by both the server dispatcher
and the agent's :class:`RemoteBackend`) so the two sides can never disagree.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from re_agent.backend.protocol import REBackend
from re_agent.core.models import FunctionTarget
from re_agent.transport import wire

# -- subjects ---------------------------------------------------------------

_PREFIX = "re"
ORCH_QUEUE = "orch"  # queue group so multiple orchestrator workers share load


def rpc_subject(project: str) -> str:
    return f"{_PREFIX}.{project}.rpc"


def job_request_subject(project: str) -> str:
    return f"{_PREFIX}.{project}.job.request"


def job_submit_subject(project: str) -> str:
    return f"{_PREFIX}.{project}.job.submit"


def events_subject(project: str) -> str:
    return f"{_PREFIX}.{project}.events"


# -- RPC ops ----------------------------------------------------------------

OP_CAPABILITIES = "capabilities"
OP_DECOMPILE = "decompile"
OP_XREFS_TO = "xrefs_to"
OP_XREFS_FROM = "xrefs_from"
OP_GET_STRUCT = "get_struct"
OP_GET_ENUM = "get_enum"
OP_GET_ASM = "get_asm"
OP_SEARCH = "search"
OP_UNIMPLEMENTED = "unimplemented"
OP_REMAINING = "remaining"
OP_SOURCE_CONTEXT = "source_context"


def dispatch(
    backend: REBackend,
    build_source_context: Callable[[FunctionTarget], str] | None,
    op: str,
    args: dict[str, Any],
) -> Any:
    """Execute one RPC op against a real backend and return the JSON-safe result.

    Runs orchestrator-side (see :mod:`re_agent.server.service`).  Raises
    ``ValueError`` for an unknown op; backend exceptions propagate to the caller,
    which turns them into an ``{ok: false, error}`` reply.
    """
    if op == OP_CAPABILITIES:
        return wire.encode_capabilities(backend.capabilities)
    if op == OP_DECOMPILE:
        return wire.encode_decompile(backend.decompile(args["target"]))
    if op == OP_XREFS_TO:
        return wire.encode_xrefs(backend.xrefs_to(args["target"]))
    if op == OP_XREFS_FROM:
        return wire.encode_xrefs(backend.xrefs_from(args["target"]))
    if op == OP_GET_STRUCT:
        return wire.encode_struct(backend.get_struct(args["name"]))
    if op == OP_GET_ENUM:
        return wire.encode_enum(backend.get_enum(args["name"]))
    if op == OP_GET_ASM:
        return wire.encode_asm(backend.get_asm(args["target"]))
    if op == OP_SEARCH:
        return wire.encode_function_entries(backend.search(args["pattern"]))
    if op == OP_UNIMPLEMENTED:
        return wire.encode_function_entries(backend.unimplemented(args.get("filter_pattern")))
    if op == OP_REMAINING:
        return wire.encode_function_entries(backend.remaining(args.get("class_name")))
    if op == OP_SOURCE_CONTEXT:
        if build_source_context is None:
            return ""
        return build_source_context(wire.decode_target(args["target"]))
    raise ValueError(f"Unknown RPC op: {op!r}")


def decode_rpc_result(op: str, result: Any) -> Any:
    """Decode a JSON-safe RPC result back into the model the agent expects.

    Runs agent-side (see :class:`re_agent.worker.remote_backend.RemoteBackend`).
    """
    if op == OP_CAPABILITIES:
        return wire.decode_capabilities(result)
    if op == OP_DECOMPILE:
        return wire.decode_decompile(result)
    if op in (OP_XREFS_TO, OP_XREFS_FROM):
        return wire.decode_xrefs(result)
    if op == OP_GET_STRUCT:
        return wire.decode_struct(result)
    if op == OP_GET_ENUM:
        return wire.decode_enum(result)
    if op == OP_GET_ASM:
        return wire.decode_asm(result)
    if op in (OP_SEARCH, OP_UNIMPLEMENTED, OP_REMAINING):
        return wire.decode_function_entries(result)
    if op == OP_SOURCE_CONTEXT:
        return result if isinstance(result, str) else ""
    raise ValueError(f"Unknown RPC op: {op!r}")
