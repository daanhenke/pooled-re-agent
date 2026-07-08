"""Configuration schema dataclasses for re-agent."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectProfile:
    """Project-specific patterns and paths."""

    hook_patterns: list[str] = field(default_factory=lambda: [
        r"RH_ScopedInstall\s*\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)",
        r"RH_ScopedVirtualInstall\s*\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)",
    ])
    stub_patterns: list[str] = field(default_factory=lambda: [
        r"plugin::Call",
    ])
    stub_markers: list[str] = field(default_factory=lambda: [
        "NOTSA_UNREACHABLE",
    ])
    stub_call_prefix: str = "plugin::Call"
    class_macro: str = "RH_ScopedClass"
    source_root: str = "source/game_sa"
    source_extensions: list[str] = field(default_factory=lambda: [
        ".cpp", ".h", ".hpp",
    ])
    hooks_csv: str | None = "docs/hooks.csv"


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    # Default to the Claude Code CLI: it uses your local subscription/OAuth
    # login, so no API key is needed.  Set provider to "claude" for the API SDK.
    provider: str = "claude-code"
    model: str = "claude-opus-4-8"
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_s: int = 1800
    # Tee CLI-provider output (claude-code) to the terminal as it streams in.
    stream: bool = False


@dataclass
class BackendConfig:
    """Decompiler backend configuration."""

    type: str = "ghidra-bridge"
    cli_path: str = "ghidra"
    timeout_s: int = 45


@dataclass
class ParityConfig:
    """Static parity verification settings."""

    enabled: bool = True
    call_count_warn_diff: int = 3
    inline_wrapper_autoskip: bool = False
    semantic_rules_file: str | None = None
    manual_checks_file: str | None = None
    cache_dir: str = ".cache/re-agent-parity"


@dataclass
class OrchestratorConfig:
    """Orchestrator loop settings."""

    max_review_rounds: int = 4
    max_functions_per_class: int = 10
    objective_verifier_enabled: bool = True
    objective_call_count_tolerance: int = 3
    objective_control_flow_tolerance: int = 2
    # When serving pooled agents, how long a handed-out function stays leased to
    # an agent before it is considered abandoned and re-offered to another agent.
    job_lease_s: int = 900
    # When False, `serve` only hands out explicitly enqueued functions (no greedy
    # unimplemented/remaining fallback). Useful when the backend's auto-list is
    # capped or you want full control over what gets reversed.
    auto_pick: bool = True
    # Optional scope for `serve`: restrict handed-out work to these classes.
    # Empty means the whole project (backend.remaining(None)).
    classes: list[str] = field(default_factory=list)


@dataclass
class TransportConfig:
    """NATS transport settings shared by the orchestrator (``serve``) and agents.

    Both sides dial *outbound* to the same NATS server(s), so neither needs port
    forwarding.  ``project`` is the subject namespace that scopes a pool to one
    shared project; together with the NATS credentials it acts as the join key.
    """

    servers: list[str] = field(default_factory=lambda: ["nats://127.0.0.1:4222"])
    project: str = "default"
    # Auth — use exactly one of: a NATS .creds file, a token, or user/password.
    creds_file: str | None = None
    token: str | None = None
    user: str | None = None
    password: str | None = None
    # TLS to the NATS server.
    tls: bool = False
    tls_ca_file: str | None = None
    connect_timeout_s: int = 10
    request_timeout_s: int = 120


@dataclass
class AgentConfig:
    """Worker-side settings for a pooled agent (``re-agent agent``).

    The agent's owner supplies the LLM provider/model/key via the ``llm``
    section; this section covers only how the worker pulls and runs jobs.
    """

    agent_id: str | None = None          # defaults to a host-derived id at runtime
    concurrency: int = 1                 # jobs this agent runs in parallel
    idle_poll_s: float = 5.0             # wait before re-asking when no work
    # If set, write per-round reverser/checker prompt+response chat logs here
    # (one subdirectory per function). Off by default.
    log_dir: str | None = None


@dataclass
class OutputConfig:
    """Output and reporting settings."""

    report_dir: str = "reports/re-agent"
    log_dir: str = "reports/re-agent/logs"
    session_file: str = "re-agent-progress.json"
    format: str = "json"


@dataclass
class ReAgentConfig:
    """Top-level configuration for the re-agent system."""

    project_profile: ProjectProfile = field(default_factory=ProjectProfile)
    llm: LLMConfig = field(default_factory=LLMConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    parity: ParityConfig = field(default_factory=ParityConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    transport: TransportConfig = field(default_factory=TransportConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    @classmethod
    def create_default(cls) -> ReAgentConfig:
        """Create a configuration with all default values."""
        return cls(
            project_profile=ProjectProfile(),
            llm=LLMConfig(),
            backend=BackendConfig(),
            parity=ParityConfig(),
            orchestrator=OrchestratorConfig(),
            output=OutputConfig(),
            transport=TransportConfig(),
            agent=AgentConfig(),
        )
