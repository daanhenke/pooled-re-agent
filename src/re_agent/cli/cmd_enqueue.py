"""re-agent enqueue — push functions onto a running orchestrator's work queue."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from re_agent.config.loader import load_config


def _read_address_file(path: str) -> list[str]:
    out: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        tok = line.strip()
        if tok and not tok.startswith("#"):
            out.append(tok.split()[0])  # tolerate "addr  name" lines
    return out


async def _enqueue(config: Any, addresses: list[str], filt: str | None) -> dict[str, Any]:
    from re_agent.transport import protocol as proto
    from re_agent.transport.nats_conn import NatsTransport

    transport = await NatsTransport.connect(config.transport, name="enqueue")
    try:
        return await transport.request(
            proto.enqueue_subject(config.transport.project),
            {"addresses": addresses, "filter": filt},
            float(config.transport.request_timeout_s),
        )
    finally:
        await transport.close()


def cmd_enqueue(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    if getattr(args, "project", None):
        config.transport.project = args.project

    addresses: list[str] = list(args.address or [])
    if args.file:
        addresses += _read_address_file(args.file)

    if not addresses and not args.filter:
        print("Error: specify at least one --address, --file, or --filter", file=sys.stderr)
        return 1

    try:
        reply = asyncio.run(_enqueue(config, addresses, args.filter))
    except Exception as exc:  # noqa: BLE001 — surface a friendly hint
        print(f"Enqueue failed: {exc}", file=sys.stderr)
        print("Is the orchestrator running and reachable? (re-agent serve)", file=sys.stderr)
        return 1

    if not reply.get("ok"):
        print(f"Orchestrator rejected enqueue: {reply.get('error')}", file=sys.stderr)
        return 1

    print(
        f"Enqueued {reply.get('enqueued', 0)} new target(s) "
        f"({reply.get('resolved', 0)} resolved); queue size now {reply.get('queue_size', '?')}."
    )
    return 0
