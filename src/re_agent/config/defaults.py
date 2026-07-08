"""Default configuration templates for re-agent."""
from __future__ import annotations

from typing import Any

DEFAULT_CONFIG_YAML: str = """\
# re-agent configuration
# See: https://github.com/dryxio/auto-re-agent for documentation.

project_profile:
  hook_patterns:
    - "RH_ScopedInstall\\\\s*\\\\(\\\\s*(\\\\w+)\\\\s*,\\\\s*(0x[0-9A-Fa-f]+)"
    - "RH_ScopedVirtualInstall\\\\s*\\\\(\\\\s*(\\\\w+)\\\\s*,\\\\s*(0x[0-9A-Fa-f]+)"
  stub_patterns:
    - "plugin::Call"
  stub_markers:
    - "NOTSA_UNREACHABLE"
  stub_call_prefix: "plugin::Call"
  class_macro: "RH_ScopedClass"
  source_root: "source/game_sa"
  source_extensions:
    - ".cpp"
    - ".h"
    - ".hpp"
  hooks_csv: "docs/hooks.csv"

llm:
  # claude-code uses your local `claude` CLI login (subscription) — no api_key.
  # Alternatives: claude (API) | openai | openai-compat | codex
  provider: "claude-code"
  model: "claude-opus-4-8"
  # api_key: null  # Set via RE_AGENT_LLM_API_KEY env var (only for API providers)
  # base_url: null  # Set via RE_AGENT_LLM_BASE_URL env var
  max_tokens: 4096
  temperature: 0.0
  timeout_s: 1800

backend:
  type: "ghidra-bridge"
  cli_path: "ghidra"
  timeout_s: 45

parity:
  enabled: true
  call_count_warn_diff: 3
  inline_wrapper_autoskip: false
  # semantic_rules_file: null
  # manual_checks_file: null
  cache_dir: ".cache/re-agent-parity"

orchestrator:
  max_review_rounds: 4
  max_functions_per_class: 10
  objective_verifier_enabled: true
  objective_call_count_tolerance: 3
  objective_control_flow_tolerance: 2

output:
  report_dir: "reports/re-agent"
  log_dir: "reports/re-agent/logs"
  session_file: "re-agent-progress.json"
  format: "json"

# Only needed when pooling agents over NATS (re-agent serve / re-agent agent).
# For a purely local run this section can be ignored.
transport:
  servers:
    - "nats://127.0.0.1:4222"
  project: "default"        # subject namespace shared by orchestrator + agents
  # creds_file: "orchestrator.creds"   # or token / user+password
  # tls: false
"""

# Orchestrator (project host) config: owns Ghidra, source tree, parity, session.
ORCHESTRATOR_CONFIG_YAML: str = """\
# re-agent ORCHESTRATOR config (project host)
# Owns the Ghidra bridge, source tree, parity engine, and session state, and
# serves jobs to pooled agents over NATS.  Run with: re-agent serve

project_profile:
  hook_patterns:
    - "RH_ScopedInstall\\\\s*\\\\(\\\\s*(\\\\w+)\\\\s*,\\\\s*(0x[0-9A-Fa-f]+)"
    - "RH_ScopedVirtualInstall\\\\s*\\\\(\\\\s*(\\\\w+)\\\\s*,\\\\s*(0x[0-9A-Fa-f]+)"
  stub_markers:
    - "NOTSA_UNREACHABLE"
  stub_call_prefix: "plugin::Call"
  source_root: "source/game_sa"
  hooks_csv: "docs/hooks.csv"

backend:
  type: "ghidra-bridge"
  cli_path: "ghidra"
  timeout_s: 45

parity:
  enabled: true

orchestrator:
  max_review_rounds: 4
  objective_verifier_enabled: true
  job_lease_s: 900

output:
  report_dir: "reports/re-agent"
  session_file: "re-agent-progress.json"

transport:
  servers:
    - "nats://YOUR_NATS_HOST:4222"
  project: "game_sa"        # must match every agent's transport.project
  creds_file: "orchestrator.creds"
  # tls: true
"""

# Agent (volunteer) config: owns the LLM key/model, needs no Ghidra/source tree.
AGENT_CONFIG_YAML: str = """\
# re-agent AGENT config (volunteer / pooled worker)
# Brings your own LLM provider + key.  Needs NO Ghidra and NO source tree — it
# proxies every RE tool call back to the orchestrator.  Run with: re-agent agent

llm:
  # claude-code and codex use your local CLI login (subscription) — no api_key.
  provider: "claude-code"   # claude-code | codex | claude | openai | openai-compat
  model: "claude-opus-4-8"
  # api_key: null           # set via RE_AGENT_LLM_API_KEY env var (API providers only)
  timeout_s: 1800

agent:
  # agent_id: null          # defaults to a host-derived id
  concurrency: 1            # jobs to run in parallel
  idle_poll_s: 5.0

transport:
  servers:
    - "nats://YOUR_NATS_HOST:4222"
  project: "game_sa"        # must match the orchestrator's transport.project
  creds_file: "agent.creds"
  # tls: true
"""

ROLE_CONFIG_TEMPLATES: dict[str, str] = {
    "orchestrator": ORCHESTRATOR_CONFIG_YAML,
    "agent": AGENT_CONFIG_YAML,
}

EXAMPLE_PROFILE_TEMPLATES: dict[str, dict[str, Any]] = {
    "gta-reversed": {
        "hook_patterns": [
            r"RH_ScopedInstall\s*\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)",
            r"RH_ScopedVirtualInstall\s*\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)",
        ],
        "stub_patterns": [
            r"plugin::Call",
        ],
        "stub_markers": [
            "NOTSA_UNREACHABLE",
        ],
        "stub_call_prefix": "plugin::Call",
        "class_macro": "RH_ScopedClass",
        "source_root": "source/game_sa",
        "source_extensions": [".cpp", ".h", ".hpp"],
        "hooks_csv": "docs/hooks.csv",
    },
    "openrct2": {
        "hook_patterns": [
            r"HOOK_FUNCTION\s*\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)",
        ],
        "stub_patterns": [
            r"original_function\(",
        ],
        "stub_markers": [
            "NOT_IMPLEMENTED",
        ],
        "stub_call_prefix": "original_function",
        "class_macro": "",
        "source_root": "src",
        "source_extensions": [".cpp", ".h", ".hpp"],
        "hooks_csv": None,
    },
}
