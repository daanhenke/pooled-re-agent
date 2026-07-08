"""Pooled-agent entry point (``re-agent agent``).

Runs an asyncio loop for the NATS connection and drives one or more concurrent
"slots".  Each slot pulls a job, runs the *synchronous* fix loop in a worker
thread (bridging its proxied backend calls back onto the event loop), and
submits the result.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from re_agent.agents.loop import run_fix_loop
from re_agent.config.schema import ReAgentConfig
from re_agent.core.models import FunctionTarget, ReversalResult
from re_agent.llm.protocol import LLMProvider
from re_agent.llm.registry import create_provider
from re_agent.transport import protocol as proto
from re_agent.transport import wire
from re_agent.transport.nats_conn import NatsTransport
from re_agent.worker.remote_backend import BlockingRequest, RemoteBackend, RpcClient
from re_agent.worker.remote_source_context import RemoteSourceContextProvider

logger = logging.getLogger(__name__)


def _default_agent_id() -> str:
    import socket

    try:
        host = socket.gethostname()
    except OSError:
        host = "agent"
    return f"{host}-{uuid.uuid4().hex[:6]}"


def _run_one_job(
    target: FunctionTarget,
    job_cfg: dict[str, Any],
    llm: LLMProvider,
    project: str,
    request: BlockingRequest,
) -> ReversalResult:
    """Synchronous: run the fix loop for one function against the remote backend.

    Executes in a worker thread.  All Ghidra/source access goes through
    ``request`` (proxied to the orchestrator); no local Ghidra or source tree.
    """
    rpc = RpcClient(project, request)
    backend = RemoteBackend(rpc)
    source_context = RemoteSourceContextProvider(rpc)

    return run_fix_loop(
        target=target,
        backend=backend,
        reverser_llm=llm,
        checker_llm=llm,
        max_rounds=int(job_cfg.get("max_rounds", 4)),
        source_context=source_context,
        objective_verifier_enabled=bool(job_cfg.get("objective_verifier_enabled", True)),
        objective_call_count_tolerance=int(job_cfg.get("objective_call_count_tolerance", 3)),
        objective_control_flow_tolerance=int(job_cfg.get("objective_control_flow_tolerance", 2)),
    )


async def run_agent(config: ReAgentConfig) -> None:
    agent_id = config.agent.agent_id or _default_agent_id()
    project = config.transport.project
    timeout = float(config.transport.request_timeout_s)

    transport = await NatsTransport.connect(config.transport, name=f"agent:{agent_id}")
    loop = asyncio.get_running_loop()

    def blocking_request(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Called from a worker thread; hop back onto the event loop for the RPC.
        fut = asyncio.run_coroutine_threadsafe(
            transport.request(subject, payload, timeout), loop
        )
        return fut.result()

    logger.info("Agent %s joined project %r via %s", agent_id, project, config.transport.servers)
    print(f"Agent {agent_id} online — project '{project}', concurrency {config.agent.concurrency}")

    async def slot(slot_idx: int) -> None:
        llm = create_provider(config.llm)  # one provider per slot (own creds)
        while True:
            try:
                reply = await transport.request(
                    proto.job_request_subject(project),
                    {"agent_id": agent_id, "model": config.llm.model, "provider": config.llm.provider},
                    timeout,
                )
            except Exception as exc:
                logger.warning("[slot %d] job request failed: %s", slot_idx, exc)
                await asyncio.sleep(config.agent.idle_poll_s)
                continue

            target_d = reply.get("target")
            if not target_d:
                await asyncio.sleep(config.agent.idle_poll_s)
                continue

            target = wire.decode_target(target_d)
            job_cfg = reply.get("config", {})
            label = f"{target.class_name}::{target.function_name} ({target.address})"
            print(f"[slot {slot_idx}] reversing {label} ...")

            try:
                result = await loop.run_in_executor(
                    None, _run_one_job, target, job_cfg, llm, project, blocking_request
                )
            except Exception as exc:
                logger.exception("[slot %d] job failed for %s", slot_idx, label)
                # Report the failure so the orchestrator releases the lease and
                # re-offers the function to another agent.
                await _submit_error(transport, project, agent_id, target, str(exc), timeout)
                continue

            try:
                ack = await transport.request(
                    proto.job_submit_subject(project),
                    {"agent_id": agent_id, "result": wire.encode_reversal_result(result)},
                    timeout,
                )
                status = ack.get("parity_status") or ("PASS" if result.success else "FAIL")
                print(f"[slot {slot_idx}] done {label}: {'PASS' if result.success else 'FAIL'} "
                      f"(rounds {result.rounds_used}, parity {status})")
            except Exception:
                logger.exception("[slot %d] failed to submit result for %s", slot_idx, label)

    await asyncio.gather(*(slot(i) for i in range(max(1, config.agent.concurrency))))


async def _submit_error(
    transport: NatsTransport,
    project: str,
    agent_id: str,
    target: FunctionTarget,
    error: str,
    timeout: float,
) -> None:
    try:
        await transport.request(
            proto.job_submit_subject(project),
            {"agent_id": agent_id, "error": error, "address": target.address},
            timeout,
        )
    except Exception:
        logger.debug("Could not report job error for %s", target.address, exc_info=True)


def run(config: ReAgentConfig) -> int:
    """Blocking entry point for the CLI."""
    try:
        asyncio.run(run_agent(config))
    except KeyboardInterrupt:
        print("\nAgent stopped.")
    return 0
