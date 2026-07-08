"""re-agent agent — run a pooled worker that reverses jobs from an orchestrator."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from re_agent.config.loader import load_config


def cmd_agent(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(Path(args.config))

    if getattr(args, "project", None):
        config.transport.project = args.project
    if getattr(args, "agent_id", None):
        config.agent.agent_id = args.agent_id
    if getattr(args, "concurrency", None):
        config.agent.concurrency = args.concurrency
    if getattr(args, "log_dir", None):
        config.agent.log_dir = args.log_dir

    from re_agent.worker.app import run

    return run(config)
