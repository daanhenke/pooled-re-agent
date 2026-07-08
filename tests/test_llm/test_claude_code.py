"""Tests for the Claude Code CLI provider (streaming plumbing)."""
from __future__ import annotations

import io

from re_agent.llm.claude_code import ClaudeCodeProvider


def test_tee_stream_returns_full_text_and_writes_live() -> None:
    sink = io.StringIO()
    text = ClaudeCodeProvider._tee_stream(["hel", "lo\n", "world\n"], sink)
    assert text == "hello\nworld\n"          # full captured output
    assert sink.getvalue() == "hello\nworld\n"  # also teed to the sink


def test_provider_defaults_non_streaming() -> None:
    p = ClaudeCodeProvider()
    assert p._stream is False
    assert p.supports_conversations is True
