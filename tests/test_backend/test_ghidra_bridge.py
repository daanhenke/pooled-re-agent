"""Tests for backend protocol and stub backend."""
from __future__ import annotations

from unittest.mock import patch

from re_agent.backend.ghidra_bridge import GhidraBridgeBackend
from re_agent.backend.protocol import BackendCapabilities, REBackend
from re_agent.backend.stub import StubBackend
from re_agent.core.models import FunctionEntry


def test_stub_backend_capabilities() -> None:
    backend = StubBackend()
    caps = backend.capabilities
    assert caps.has_decompile
    assert isinstance(caps, BackendCapabilities)


def test_stub_backend_decompile() -> None:
    backend = StubBackend()
    result = backend.decompile("0x6F86A0")
    assert result.address == "0x6F86A0"
    assert len(result.decompiled) > 0


def test_stub_backend_remaining() -> None:
    entries = [
        FunctionEntry(address="0x100", name="Foo", class_name="CTest", caller_count=5),
    ]
    backend = StubBackend(remaining_functions=entries)
    result = backend.remaining("CTest")
    assert len(result) == 1
    assert result[0].name == "Foo"


def test_stub_backend_is_re_backend() -> None:
    backend = StubBackend()
    assert isinstance(backend, REBackend)


# -- Capability probing tests -------------------------------------------------


def test_subcmd_exists_exit_zero() -> None:
    """Exit code 0 means the sub-command is available."""
    backend = GhidraBridgeBackend(cli_path="fake-ghidra")
    with patch("re_agent.backend.ghidra_bridge.run_cmd_split") as mock:
        mock.return_value = (0, "help text", "")
        assert backend._subcmd_exists("asm") is True
        mock.assert_called_once()


def test_subcmd_exists_unknown_command_in_stderr() -> None:
    """'unknown command' in stderr means the sub-command does NOT exist."""
    backend = GhidraBridgeBackend(cli_path="fake-ghidra")
    with patch("re_agent.backend.ghidra_bridge.run_cmd_split") as mock:
        mock.return_value = (1, "", "Error: unknown command 'asm'")
        assert backend._subcmd_exists("asm") is False


def test_subcmd_exists_nonzero_no_unknown_pattern() -> None:
    """Non-zero exit with no 'unknown command' pattern means available."""
    backend = GhidraBridgeBackend(cli_path="fake-ghidra")
    with patch("re_agent.backend.ghidra_bridge.run_cmd_split") as mock:
        # First call: --help returns non-zero with generic error
        # Second call: __probe__ also returns non-zero with generic error
        mock.side_effect = [
            (1, "", "Error: missing required argument"),
            (1, "", "Error: missing required argument"),
        ]
        assert backend._subcmd_exists("asm") is True


def test_subcmd_exists_unrecognized_args_not_false_negative() -> None:
    """'unrecognized arguments' should NOT cause false negatives."""
    backend = GhidraBridgeBackend(cli_path="fake-ghidra")
    with patch("re_agent.backend.ghidra_bridge.run_cmd_split") as mock:
        # --help returns non-zero with "unrecognized arguments"
        # This should NOT be treated as "unknown command"
        mock.side_effect = [
            (1, "", "error: unrecognized arguments: --help"),
            (1, "", "error: missing operand"),
        ]
        assert backend._subcmd_exists("asm") is True


# -- Function-list parsing ----------------------------------------------------


def test_parse_function_list_unimplemented_format() -> None:
    """The real `ghidra-bridge unimplemented` format: header lines skipped,
    "[N callers]" read, function name taken correctly."""
    raw = (
        "Unimplemented functions: 37269\n"
        "(Sorted by number of callers - most important first)\n"
        "\n"
        "  0x140263e80  [7723 callers]  FUN_140263e80\n"
        "  0x140265e60  [5981 callers]  FUN_140265e60\n"
        "  0x1409d4dc4  [3220 callers]  atexit\n"
    )
    entries = GhidraBridgeBackend._parse_function_list(raw)
    assert len(entries) == 3  # the two header lines are NOT parsed as functions
    assert entries[0].address == "0x140263e80"
    assert entries[0].name == "FUN_140263e80"
    assert entries[0].caller_count == 7723
    assert entries[2].name == "atexit"


def test_parse_function_list_variants() -> None:
    """No-0x addresses, Class::Func names, and trailing "(N callers)" form."""
    raw = (
        "Total functions: 2\n"
        "  140001000  FUN_140001000\n"
        "  0x5E3E90  CTrain::ProcessControl  (5 callers)\n"
    )
    entries = GhidraBridgeBackend._parse_function_list(raw)
    assert len(entries) == 2
    assert entries[0].address == "140001000" and entries[0].name == "FUN_140001000"
    assert entries[1].class_name == "CTrain"
    assert entries[1].name == "ProcessControl"
    assert entries[1].caller_count == 5
