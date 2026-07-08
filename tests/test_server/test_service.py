"""End-to-end job flow: orchestrator service + worker over the in-process bus.

No NATS broker and no real Ghidra — the FakeTransport wires the agent's proxied
tool calls straight to the service's StubBackend, exactly as production wires
them through NATS.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from re_agent.backend.stub import StubBackend
from re_agent.config.schema import ReAgentConfig
from re_agent.core.models import FunctionEntry
from re_agent.core.session import Session
from re_agent.server.service import OrchestratorService
from re_agent.transport import protocol as proto
from re_agent.transport import wire
from re_agent.transport.fake import FakeTransport
from re_agent.worker.app import _run_one_job


class MockLLM:
    """Serves reverser then checker responses in call order."""

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


def _make_config(tmp_path: Path) -> ReAgentConfig:
    config = ReAgentConfig()
    config.transport.project = "testproj"
    config.parity.enabled = False  # no source tree in this test
    config.output.session_file = str(tmp_path / "progress.json")
    config.output.report_dir = str(tmp_path / "reports")
    config.output.log_dir = ""
    return config


@pytest.mark.asyncio
async def test_full_job_flow(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    session = Session(config.output.session_file)
    backend = StubBackend(
        remaining_functions=[
            FunctionEntry(address="0x6F86A0", name="ProcessControl", class_name="CTrain", caller_count=5),
        ]
    )
    service = OrchestratorService(config, backend, session, indexer=None, source_ctx=None)
    bus = FakeTransport()
    await service.subscribe(bus)

    project = "testproj"
    loop = asyncio.get_running_loop()

    def blocking_request(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run_coroutine_threadsafe(bus.request(subject, payload, 30), loop).result()

    # 1. Agent asks for work and is leased the highest-caller function.
    reply = await bus.request(proto.job_request_subject(project), {"agent_id": "t1"}, 30)
    assert reply["target"] is not None
    target = wire.decode_target(reply["target"])
    assert target.address == "0x6F86A0"

    # 2. A second agent gets nothing — the function is leased, not double-assigned.
    reply2 = await bus.request(proto.job_request_subject(project), {"agent_id": "t2"}, 30)
    assert reply2["target"] is None

    # 3. Run the reversal in a worker thread; its backend calls proxy to the service.
    llm = MockLLM([
        "```cpp\nvoid CTrain::ProcessControl() { }\n```\nREVERSED_FUNCTION: x",
        "VERDICT: PASS\nSUMMARY: ok\nISSUES:\n- none\nFIX_INSTRUCTIONS:\n- none",
    ])
    result = await loop.run_in_executor(
        None, _run_one_job, target, reply["config"], llm, project, blocking_request
    )
    assert result.success

    # 4. Submit — orchestrator finalizes and records it, clearing the lease.
    ack = await bus.request(
        proto.job_submit_subject(project),
        {"agent_id": "t1", "result": wire.encode_reversal_result(result)},
        30,
    )
    assert ack["ok"] is True
    assert session.is_completed("0x6F86A0")

    # 5. No more work remains.
    reply3 = await bus.request(proto.job_request_subject(project), {"agent_id": "t3"}, 30)
    assert reply3["target"] is None


@pytest.mark.asyncio
async def test_job_error_releases_lease(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    session = Session(config.output.session_file)
    backend = StubBackend(
        remaining_functions=[
            FunctionEntry(address="0x700000", name="Foo", class_name="CTrain", caller_count=2),
        ]
    )
    service = OrchestratorService(config, backend, session, indexer=None, source_ctx=None)
    bus = FakeTransport()
    await service.subscribe(bus)
    project = "testproj"

    reply = await bus.request(proto.job_request_subject(project), {"agent_id": "t1"}, 30)
    target = wire.decode_target(reply["target"])
    assert session.is_in_progress(target.address)

    # Agent reports a failure -> lease released -> function offered again.
    ack = await bus.request(
        proto.job_submit_subject(project),
        {"agent_id": "t1", "error": "boom", "address": target.address},
        30,
    )
    assert ack["ok"] is True
    assert not session.is_in_progress(target.address)

    reply2 = await bus.request(proto.job_request_subject(project), {"agent_id": "t2"}, 30)
    assert reply2["target"] is not None
    assert wire.decode_target(reply2["target"]).address == "0x700000"
