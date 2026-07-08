"""Orchestrator entry point (``re-agent serve``).

Builds the real backend, source tree, indexer, and session, then connects to
NATS and serves pooled agents forever.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from re_agent.agents.source_context import SourceContextBuilder
from re_agent.backend.registry import create_backend
from re_agent.config.schema import ReAgentConfig
from re_agent.core.session import Session
from re_agent.parity.source_indexer import SourceIndexer
from re_agent.server.service import OrchestratorService
from re_agent.transport.nats_conn import NatsTransport

logger = logging.getLogger(__name__)


async def run_server(config: ReAgentConfig) -> None:
    backend = create_backend(config.backend)
    session = Session(config.output.session_file)

    source_root = Path(config.project_profile.source_root)
    indexer: SourceIndexer | None = None
    source_ctx: SourceContextBuilder | None = None
    if source_root.exists():
        indexer = SourceIndexer(source_root, config.project_profile)
        source_ctx = SourceContextBuilder(
            source_root=source_root,
            profile=config.project_profile,
            indexer=indexer,
            session=session,
            report_dir=Path(config.output.report_dir),
        )
    else:
        logger.warning(
            "Source root %s not found — source-context RPCs return empty and parity may degrade",
            source_root,
        )

    # Construct the service inside the running loop so its asyncio locks bind here.
    service = OrchestratorService(config, backend, session, indexer, source_ctx)

    transport = await NatsTransport.connect(config.transport, name="orchestrator")
    try:
        await service.serve(transport)
    finally:
        await transport.close()


def run(config: ReAgentConfig) -> int:
    """Blocking entry point for the CLI."""
    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        print("\nOrchestrator stopped.")
    return 0
