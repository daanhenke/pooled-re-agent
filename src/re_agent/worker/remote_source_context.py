"""Source-context provider that fetches from the orchestrator over NATS.

The orchestrator holds the source tree, so the reverser's nearby-source
retrieval becomes one more proxied tool call (``source_context``).  Satisfies
:class:`re_agent.agents.source_context.SourceContextProvider`.
"""
from __future__ import annotations

from re_agent.core.models import FunctionTarget
from re_agent.transport import protocol as proto
from re_agent.transport import wire
from re_agent.worker.remote_backend import RpcClient


class RemoteSourceContextProvider:
    """Fetches reverser source context from the orchestrator."""

    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def build(self, target: FunctionTarget) -> str:
        result = self._rpc.call(proto.OP_SOURCE_CONTEXT, {"target": wire.encode_target(target)})
        return result if isinstance(result, str) else ""
