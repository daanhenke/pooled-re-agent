"""JSON (de)serialization for the dataclasses that cross the NATS wire.

Every function has an ``encode_*`` (object -> plain dict) and ``decode_*``
(plain dict -> object) counterpart so the RPC surface is symmetric and easy to
test.  Enums are carried by their ``.value``.  ``None`` is passed through for the
optional-returning backend methods (``get_struct``/``get_enum``/``get_asm``).

Only these types cross the boundary, matching the calls the reverser/checker/
objective loop makes through :class:`re_agent.backend.protocol.REBackend`, plus
the job-assignment/result types.
"""
from __future__ import annotations

from typing import Any

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

# ---------------------------------------------------------------------------
# Backend capabilities
# ---------------------------------------------------------------------------

def encode_capabilities(caps: BackendCapabilities) -> dict[str, Any]:
    return {
        "has_decompile": caps.has_decompile,
        "has_asm": caps.has_asm,
        "has_structs": caps.has_structs,
        "has_xrefs": caps.has_xrefs,
        "has_search": caps.has_search,
        "has_enums": caps.has_enums,
    }


def decode_capabilities(d: dict[str, Any]) -> BackendCapabilities:
    return BackendCapabilities(
        has_decompile=d.get("has_decompile", True),
        has_asm=d.get("has_asm", False),
        has_structs=d.get("has_structs", False),
        has_xrefs=d.get("has_xrefs", True),
        has_search=d.get("has_search", True),
        has_enums=d.get("has_enums", False),
    )


# ---------------------------------------------------------------------------
# Decompile
# ---------------------------------------------------------------------------

def encode_decompile(r: DecompileResult) -> dict[str, Any]:
    return {
        "address": r.address,
        "name": r.name,
        "signature": r.signature,
        "decompiled": r.decompiled,
        "raw_output": r.raw_output,
        "callers": r.callers,
        "callees": r.callees,
    }


def decode_decompile(d: dict[str, Any]) -> DecompileResult:
    return DecompileResult(
        address=d["address"],
        name=d["name"],
        signature=d.get("signature", ""),
        decompiled=d.get("decompiled", ""),
        raw_output=d.get("raw_output", ""),
        callers=d.get("callers"),
        callees=d.get("callees"),
    )


# ---------------------------------------------------------------------------
# XRefs
# ---------------------------------------------------------------------------

def encode_xref(x: XRef) -> dict[str, Any]:
    return {"address": x.address, "name": x.name, "ref_type": x.ref_type}


def decode_xref(d: dict[str, Any]) -> XRef:
    return XRef(address=d["address"], name=d.get("name", ""), ref_type=d.get("ref_type", ""))


def encode_xrefs(xs: list[XRef]) -> list[dict[str, Any]]:
    return [encode_xref(x) for x in xs]


def decode_xrefs(items: list[dict[str, Any]]) -> list[XRef]:
    return [decode_xref(d) for d in items]


# ---------------------------------------------------------------------------
# Structs
# ---------------------------------------------------------------------------

def encode_struct(s: StructDef | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "name": s.name,
        "size": s.size,
        "fields": [
            {"name": f.name, "offset": f.offset, "type_str": f.type_str, "size": f.size}
            for f in s.fields
        ],
    }


def decode_struct(d: dict[str, Any] | None) -> StructDef | None:
    if d is None:
        return None
    return StructDef(
        name=d["name"],
        size=d.get("size", 0),
        fields=[
            StructField(
                name=f["name"], offset=f.get("offset", 0),
                type_str=f.get("type_str", ""), size=f.get("size", 0),
            )
            for f in d.get("fields", [])
        ],
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def encode_enum(e: EnumDef | None) -> dict[str, Any] | None:
    if e is None:
        return None
    return {"name": e.name, "values": [{"name": v.name, "value": v.value} for v in e.values]}


def decode_enum(d: dict[str, Any] | None) -> EnumDef | None:
    if d is None:
        return None
    return EnumDef(
        name=d["name"],
        values=[EnumValue(name=v["name"], value=v["value"]) for v in d.get("values", [])],
    )


# ---------------------------------------------------------------------------
# ASM
# ---------------------------------------------------------------------------

def encode_asm(a: AsmResult | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "address": a.address,
        "instructions": a.instructions,
        "instruction_count": a.instruction_count,
        "call_count": a.call_count,
        "has_fp_sensitive": a.has_fp_sensitive,
    }


def decode_asm(d: dict[str, Any] | None) -> AsmResult | None:
    if d is None:
        return None
    return AsmResult(
        address=d["address"],
        instructions=d.get("instructions", ""),
        instruction_count=d.get("instruction_count", 0),
        call_count=d.get("call_count", 0),
        has_fp_sensitive=d.get("has_fp_sensitive", False),
    )


# ---------------------------------------------------------------------------
# Function entries
# ---------------------------------------------------------------------------

def encode_function_entry(f: FunctionEntry) -> dict[str, Any]:
    return {
        "address": f.address,
        "name": f.name,
        "class_name": f.class_name,
        "caller_count": f.caller_count,
    }


def decode_function_entry(d: dict[str, Any]) -> FunctionEntry:
    return FunctionEntry(
        address=d["address"],
        name=d.get("name", ""),
        class_name=d.get("class_name", ""),
        caller_count=d.get("caller_count", 0),
    )


def encode_function_entries(fs: list[FunctionEntry]) -> list[dict[str, Any]]:
    return [encode_function_entry(f) for f in fs]


def decode_function_entries(items: list[dict[str, Any]]) -> list[FunctionEntry]:
    return [decode_function_entry(d) for d in items]


# ---------------------------------------------------------------------------
# Function target (job assignment)
# ---------------------------------------------------------------------------

def encode_target(t: FunctionTarget) -> dict[str, Any]:
    return {
        "address": t.address,
        "class_name": t.class_name,
        "function_name": t.function_name,
        "caller_count": t.caller_count,
    }


def decode_target(d: dict[str, Any]) -> FunctionTarget:
    return FunctionTarget(
        address=d["address"],
        class_name=d.get("class_name", ""),
        function_name=d.get("function_name", ""),
        caller_count=d.get("caller_count", 0),
    )


# ---------------------------------------------------------------------------
# Verdicts / findings / results
# ---------------------------------------------------------------------------

def encode_checker_verdict(v: CheckerVerdict | None) -> dict[str, Any] | None:
    if v is None:
        return None
    return {
        "verdict": v.verdict.value,
        "summary": v.summary,
        "issues": list(v.issues),
        "fix_instructions": list(v.fix_instructions),
    }


def decode_checker_verdict(d: dict[str, Any] | None) -> CheckerVerdict | None:
    if d is None:
        return None
    return CheckerVerdict(
        verdict=Verdict(d.get("verdict", "UNKNOWN")),
        summary=d.get("summary", ""),
        issues=list(d.get("issues", [])),
        fix_instructions=list(d.get("fix_instructions", [])),
    )


def encode_objective_verdict(v: ObjectiveVerdict | None) -> dict[str, Any] | None:
    if v is None:
        return None
    return {"verdict": v.verdict.value, "summary": v.summary, "findings": list(v.findings)}


def decode_objective_verdict(d: dict[str, Any] | None) -> ObjectiveVerdict | None:
    if d is None:
        return None
    return ObjectiveVerdict(
        verdict=Verdict(d.get("verdict", "UNKNOWN")),
        summary=d.get("summary", ""),
        findings=list(d.get("findings", [])),
    )


def encode_finding(f: Finding) -> dict[str, Any]:
    return {"level": f.level, "reason": f.reason}


def decode_finding(d: dict[str, Any]) -> Finding:
    return Finding(level=d.get("level", "info"), reason=d.get("reason", ""))


def encode_reversal_result(r: ReversalResult) -> dict[str, Any]:
    return {
        "target": encode_target(r.target),
        "code": r.code,
        "checker_verdict": encode_checker_verdict(r.checker_verdict),
        "objective_verdict": encode_objective_verdict(r.objective_verdict),
        "parity_status": r.parity_status.value if r.parity_status else None,
        "parity_findings": [encode_finding(f) for f in r.parity_findings],
        "rounds_used": r.rounds_used,
        "success": r.success,
    }


def decode_reversal_result(d: dict[str, Any]) -> ReversalResult:
    parity_status = d.get("parity_status")
    return ReversalResult(
        target=decode_target(d["target"]),
        code=d.get("code", ""),
        checker_verdict=decode_checker_verdict(d.get("checker_verdict")),
        objective_verdict=decode_objective_verdict(d.get("objective_verdict")),
        parity_status=ParityStatus(parity_status) if parity_status else None,
        parity_findings=[decode_finding(f) for f in d.get("parity_findings", [])],
        rounds_used=d.get("rounds_used", 0),
        success=d.get("success", False),
    )
