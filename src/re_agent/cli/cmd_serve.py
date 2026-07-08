"""re-agent serve — run the orchestrator server for pooled agents."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from re_agent.config.loader import load_config


def cmd_serve(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(Path(args.config))

    if getattr(args, "project", None):
        config.transport.project = args.project

    from re_agent.server.app import run

    return run(config)
