"""Round-trip tests for the wire (de)serialization of every crossing type."""
from __future__ import annotations

import json

from re_agent.backend.protocol import BackendCapabilities
from re_agent.core.models import (
    AsmResult,
    CheckerVerdict,
    DecompileResult,
    EnumDef,
    EnumValue,
    Finding,
    FunctionEntry,
    FunctionTarget,
    ObjectiveVerdict,
    ParityStatus,
    ReversalResult,
    StructDef,
    StructField,
    Verdict,
    XRef,
)
from re_agent.transport import wire


def _json_stable(obj: object) -> object:
    """Ensure the encoded form is actually JSON-serializable."""
    return json.loads(json.dumps(obj))


def test_capabilities_round_trip() -> None:
    caps = BackendCapabilities(has_asm=True, has_structs=True, has_enums=False)
    out = wire.decode_capabilities(_json_stable(wire.encode_capabilities(caps)))
    assert out == caps


def test_decompile_round_trip() -> None:
    d = DecompileResult(
        address="0x6F86A0", name="CTrain::Foo", signature="void Foo()",
        decompiled="body", raw_output="raw", callers=5, callees=3,
    )
    out = wire.decode_decompile(_json_stable(wire.encode_decompile(d)))
    assert out == d


def test_xrefs_round_trip() -> None:
    xs = [XRef(address="0x1", name="A", ref_type="CALL"), XRef(address="0x2", name="B", ref_type="DATA")]
    out = wire.decode_xrefs(_json_stable(wire.encode_xrefs(xs)))
    assert out == xs


def test_struct_round_trip_and_none() -> None:
    s = StructDef(name="CTrain", size=0x40, fields=[StructField(name="m_x", offset=4, type_str="int", size=4)])
    out = wire.decode_struct(_json_stable(wire.encode_struct(s)))
    assert out == s
    assert wire.encode_struct(None) is None
    assert wire.decode_struct(None) is None


def test_enum_round_trip_and_none() -> None:
    e = EnumDef(name="eState", values=[EnumValue(name="OFF", value=0), EnumValue(name="ON", value=1)])
    out = wire.decode_enum(_json_stable(wire.encode_enum(e)))
    assert out == e
    assert wire.encode_enum(None) is None


def test_asm_round_trip_and_none() -> None:
    a = AsmResult(address="0x1", instructions="CALL x", instruction_count=1, call_count=1, has_fp_sensitive=True)
    out = wire.decode_asm(_json_stable(wire.encode_asm(a)))
    assert out == a
    assert wire.encode_asm(None) is None


def test_function_entries_round_trip() -> None:
    fs = [FunctionEntry(address="0x1", name="Foo", class_name="CTrain", caller_count=7)]
    out = wire.decode_function_entries(_json_stable(wire.encode_function_entries(fs)))
    assert out == fs


def test_target_round_trip() -> None:
    t = FunctionTarget(address="0x6F86A0", class_name="CTrain", function_name="Foo", caller_count=9)
    out = wire.decode_target(_json_stable(wire.encode_target(t)))
    assert out == t


def test_reversal_result_round_trip() -> None:
    result = ReversalResult(
        target=FunctionTarget(address="0x1", class_name="C", function_name="f"),
        code="void f(){}",
        checker_verdict=CheckerVerdict(Verdict.PASS, "ok", ["i"], ["fix"]),
        objective_verdict=ObjectiveVerdict(Verdict.PASS, "ok", ["finding"]),
        parity_status=ParityStatus.GREEN,
        parity_findings=[Finding(level="yellow", reason="short body")],
        rounds_used=2,
        success=True,
    )
    out = wire.decode_reversal_result(_json_stable(wire.encode_reversal_result(result)))
    assert out == result


def test_reversal_result_round_trip_with_nones() -> None:
    result = ReversalResult(
        target=FunctionTarget(address="0x1", class_name="", function_name=""),
        code="",
        checker_verdict=None,
        objective_verdict=None,
        parity_status=None,
        parity_findings=[],
        rounds_used=0,
        success=False,
    )
    out = wire.decode_reversal_result(_json_stable(wire.encode_reversal_result(result)))
    assert out == result
