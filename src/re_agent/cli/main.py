"""CLI entry point for re-agent."""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="re-agent",
        description="Autonomous reverse engineering agent",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument("--config", default="re-agent.yaml", help="Config file path")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_p = sub.add_parser("init", help="Initialize re-agent.yaml config file")
    init_p.add_argument("--profile", default=None, help="Use a built-in project profile template")
    init_p.add_argument(
        "--role",
        choices=["orchestrator", "agent"],
        default=None,
        help="Emit a role-specific config (orchestrator server or pooled agent)",
    )

    # reverse
    rev_p = sub.add_parser("reverse", help="Reverse engineer functions")
    rev_p.add_argument("--address", help="Single function address to reverse")
    rev_p.add_argument("--class", dest="class_name", help="Class name for class-level reversal")
    rev_p.add_argument("--max-functions", type=int, default=None, help="Max functions per class")
    rev_p.add_argument("--max-rounds", type=int, default=None, help="Max review rounds per function")
    rev_p.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    rev_p.add_argument("--skip-parity", action="store_true", help="Skip parity check after PASS")

    # parity
    par_p = sub.add_parser("parity", help="Run parity checks on hooked functions")
    par_p.add_argument("--address", action="append", help="Specific address (repeatable)")
    par_p.add_argument("--filter", help="Regex filter on symbol/class")
    par_p.add_argument("--limit", type=int, help="Max functions to check")
    par_p.add_argument("--skip-ghidra", action="store_true", help="Source-only checks")
    par_p.add_argument("--strict-exit", action="store_true", help="Exit 1 on RED")
    par_p.add_argument("--output", help="Output JSON report path")

    # status
    stat_p = sub.add_parser("status", help="Show reversal progress")
    stat_p.add_argument("--class", dest="class_name", help="Filter by class")
    stat_p.add_argument("--format", choices=["text", "json", "markdown"], default="text")

    # serve (orchestrator)
    serve_p = sub.add_parser("serve", help="Run the orchestrator server for pooled agents")
    serve_p.add_argument("--project", default=None, help="Override transport.project (subject namespace)")

    # agent (pooled worker)
    agent_p = sub.add_parser("agent", help="Run a pooled worker connected to an orchestrator")
    agent_p.add_argument("--project", default=None, help="Override transport.project (subject namespace)")
    agent_p.add_argument("--agent-id", dest="agent_id", default=None, help="Override this agent's id")
    agent_p.add_argument("--concurrency", type=int, default=None, help="Jobs to run in parallel")
    agent_p.add_argument("--log-dir", dest="log_dir", default=None,
                         help="Write per-round reverser/checker chat logs to this directory")

    # enqueue (push work to a running orchestrator)
    enq_p = sub.add_parser("enqueue", help="Enqueue functions for the pool to reverse (priority over auto-pick)")
    enq_p.add_argument("--address", action="append", help="Address to enqueue (repeatable)")
    enq_p.add_argument("--filter", help="Enqueue all unimplemented functions matching this pattern")
    enq_p.add_argument("--file", help="File with one address per line")
    enq_p.add_argument("--project", default=None, help="Override transport.project (subject namespace)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        from re_agent.cli.cmd_init import cmd_init
        return cmd_init(args)

    if args.command == "reverse":
        from re_agent.cli.cmd_reverse import cmd_reverse
        return cmd_reverse(args)

    if args.command == "parity":
        from re_agent.cli.cmd_parity import cmd_parity
        return cmd_parity(args)

    if args.command == "status":
        from re_agent.cli.cmd_status import cmd_status
        return cmd_status(args)

    if args.command == "serve":
        from re_agent.cli.cmd_serve import cmd_serve
        return cmd_serve(args)

    if args.command == "agent":
        from re_agent.cli.cmd_agent import cmd_agent
        return cmd_agent(args)

    if args.command == "enqueue":
        from re_agent.cli.cmd_enqueue import cmd_enqueue
        return cmd_enqueue(args)

    parser.print_help()
    return 1
