"""re-agent init command — generates config file."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from re_agent.config.defaults import (
    DEFAULT_CONFIG_YAML,
    EXAMPLE_PROFILE_TEMPLATES,
    ROLE_CONFIG_TEMPLATES,
)


def cmd_init(args: argparse.Namespace) -> int:
    config_path = Path(args.config)

    if config_path.exists():
        print(f"Config already exists: {config_path}")
        print("Delete it first if you want to regenerate.")
        return 1

    # Role-specific templates (orchestrator / agent) short-circuit the
    # profile-overlay path below — they are purpose-built starting points.
    role = getattr(args, "role", None)
    if role:
        if role not in ROLE_CONFIG_TEMPLATES:
            available = ", ".join(ROLE_CONFIG_TEMPLATES)
            print(f"Unknown role: {role}")
            print(f"Available roles: {available}")
            return 1
        config_path.write_text(ROLE_CONFIG_TEMPLATES[role], encoding="utf-8")
        print(f"Created {config_path} for role '{role}'")
        if role == "agent":
            print("Set your LLM key (RE_AGENT_LLM_API_KEY) and point transport at the NATS server.")
        else:
            print("Point backend.cli_path at Ghidra and transport at the NATS server, then: re-agent serve")
        return 0

    content = DEFAULT_CONFIG_YAML

    if args.profile and args.profile in EXAMPLE_PROFILE_TEMPLATES:
        print(f"Using profile template: {args.profile}")
        # Parse the default YAML, overlay the profile, and re-serialize
        data = yaml.safe_load(content)
        profile_overrides = EXAMPLE_PROFILE_TEMPLATES[args.profile]
        if "project_profile" not in data:
            data["project_profile"] = {}
        for key, value in profile_overrides.items():
            data["project_profile"][key] = value
        content = "# re-agent configuration\n"
        content += f"# Profile: {args.profile}\n\n"
        content += yaml.dump(data, default_flow_style=False, sort_keys=False)
    elif args.profile:
        available = ", ".join(EXAMPLE_PROFILE_TEMPLATES)
        print(f"Unknown profile: {args.profile}")
        print(f"Available profiles: {available}")
        return 1

    config_path.write_text(content, encoding="utf-8")
    print(f"Created {config_path}")
    print("Edit it to configure your LLM provider, backend, and project profile.")
    return 0
