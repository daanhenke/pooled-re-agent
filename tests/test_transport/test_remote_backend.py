"""RemoteBackend over an in-process sync dispatch bridge.

Wires RemoteBackend -> proto.dispatch -> a real StubBackend so the whole RPC
surface (encode on the server, decode on the agent) is exercised, and the
existing fix loop runs unchanged against the proxy.
"""
from __future__ import annotations

from typing import Any

from re_agent.backend.stub import StubBackend
from re_agent.core.models import DecompileResult, FunctionTarget, Verdict
from re_agent.transport import protocol as proto
from re_agent.worker.remote_backend import RemoteBackend, RpcClient


class CountingBackend(StubBackend):
    """StubBackend that counts decompile calls (to verify agent-side caching)."""

    def __init__(self) -> None:
        super().__init__()
        self.decompile_calls = 0

    def decompile(self, target: str) -> DecompileResult:
        self.decompile_calls += 1
        return super().decompile(target)


def make_rpc(backend: Any) -> RpcClient:
    """A synchronous RpcClient that dispatches straight to a backend."""

    def request(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = proto.dispatch(backend, None, payload["op"], payload["args"])
            return {"ok": True, "result": result}
        except Exception as exc:  # mirror the server's error envelope
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return RpcClient("test", request)


def test_remote_backend_proxies_all_ops() -> None:
    backend = StubBackend()
    rb = RemoteBackend(make_rpc(backend))

    caps = rb.capabilities
    assert caps.has_asm and caps.has_structs and caps.has_xrefs

    dec = rb.decompile("0x6F86A0")
    assert dec.name == "CStub::StubFunction"
    assert dec.callers == 2

    assert rb.xrefs_from("0x6F86A0") == []
    assert rb.get_struct("CStub") is None
    assert rb.get_enum("eThing") is None
    assert rb.get_asm("0x6F86A0") is None
    assert rb.remaining("CStub") == []


def test_remote_backend_caches_decompile() -> None:
    backend = CountingBackend()
    rb = RemoteBackend(make_rpc(backend))
    rb.decompile("0x6F86A0")
    rb.decompile("0x6F86A0")
    rb.decompile("0x6F86A0")
    assert backend.decompile_calls == 1  # memoized per instance


class MockLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._idx = 0

    def send(self, messages: list[Any], **kwargs: Any) -> str:
        idx = min(self._idx, len(self._responses) - 1)
        self._idx += 1
        return self._responses[idx]

    @property
    def supports_conversations(self) -> bool:
        return False

    def new_conversation(self, system: str) -> str:
        return ""

    def resume(self, conversation_id: str, message: str) -> str:
        return ""


def test_fix_loop_runs_against_remote_backend() -> None:
    from re_agent.agents.loop import run_fix_loop

    backend = StubBackend()
    rb = RemoteBackend(make_rpc(backend))
    target = FunctionTarget(address="0x6F86A0", class_name="CTrain", function_name="ProcessControl")

    reverser_resp = (
        "```cpp\nvoid CTrain::ProcessControl() { }\n```\n"
        "REVERSED_FUNCTION: CTrain::ProcessControl (0x6F86A0)"
    )
    checker_resp = "VERDICT: PASS\nSUMMARY: ok\nISSUES:\n- none\nFIX_INSTRUCTIONS:\n- none"

    result = run_fix_loop(target, rb, MockLLM([reverser_resp]), MockLLM([checker_resp]), max_rounds=3)
    assert result.success
    assert result.checker_verdict is not None
    assert result.checker_verdict.verdict == Verdict.PASS
