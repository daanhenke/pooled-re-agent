"""Tests for session leasing and the function picker's in-progress skip."""
from __future__ import annotations

from pathlib import Path

from re_agent.backend.stub import StubBackend
from re_agent.core.function_picker import pick_next_global
from re_agent.core.models import (
    CheckerVerdict,
    FunctionEntry,
    FunctionTarget,
    ReversalResult,
    Verdict,
)
from re_agent.core.session import Session


def _target(addr: str) -> FunctionTarget:
    return FunctionTarget(address=addr, class_name="CTrain", function_name="Foo", caller_count=1)


def test_lease_marks_and_releases(tmp_path: Path) -> None:
    session = Session(tmp_path / "s.json")
    session.mark_in_progress(_target("0x1000"), "agentA", lease_s=60)
    assert session.is_in_progress("0x1000")
    assert session.active_in_progress()  # non-empty (holds the normalized addr)

    session.release("0x1000")
    assert not session.is_in_progress("0x1000")


def test_expired_lease_is_pruned(tmp_path: Path) -> None:
    session = Session(tmp_path / "s.json")
    session.mark_in_progress(_target("0x2000"), "agentA", lease_s=-1)  # already expired
    assert not session.is_in_progress("0x2000")
    assert session.active_in_progress() == set()


def test_recording_result_clears_lease(tmp_path: Path) -> None:
    session = Session(tmp_path / "s.json")
    session.mark_in_progress(_target("0x3000"), "agentA", lease_s=60)
    session.record_result(
        ReversalResult(
            target=_target("0x3000"),
            code="void f(){}",
            checker_verdict=CheckerVerdict(Verdict.PASS, "ok"),
            success=True,
        )
    )
    assert not session.is_in_progress("0x3000")
    assert session.is_completed("0x3000")


def test_picker_skips_leased(tmp_path: Path) -> None:
    session = Session(tmp_path / "s.json")
    backend = StubBackend(
        remaining_functions=[
            FunctionEntry(address="0x4000", name="A", class_name="CTrain", caller_count=9),
            FunctionEntry(address="0x4004", name="B", class_name="CTrain", caller_count=3),
        ]
    )
    first = pick_next_global(backend, session)
    assert first is not None and first.address == "0x4000"  # highest caller count

    session.mark_in_progress(first, "agentA", lease_s=60)
    second = pick_next_global(backend, session)
    assert second is not None and second.address == "0x4004"  # skips the leased one

    session.mark_in_progress(second, "agentB", lease_s=60)
    assert pick_next_global(backend, session) is None  # nothing left
