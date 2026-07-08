# Pooling re-agent over NATS

This folder runs a NATS server that lets an **orchestrator** (project host) and
any number of **agents** (volunteers) work on one shared reversing project —
**without port forwarding on either the orchestrator or the agents**. Everyone
dials *outbound* to NATS; only the NATS host needs a reachable port.

```
 agent (laptop)                 NATS server                 orchestrator (host)
   own LLM key    ── outbound ──►  :4222  ◄── outbound ──   Ghidra + source tree
```

## 1. Start the relay

On a host both sides can reach (VPS, home server with one forwarded port, …):

```bash
docker compose -f deploy/nats/docker-compose.yml up -d
```

Edit [nats-server.conf](nats-server.conf) first and change `CHANGE_ME_SUPER_SECRET`.
For anything crossing the public internet, enable TLS (see the conf comments).

## 2. Configure the orchestrator (project host)

```bash
re-agent init --role orchestrator --config re-agent.orchestrator.yaml
```

Then edit it: point `backend.cli_path` at Ghidra, set `project_profile.source_root`,
and set the `transport` block:

```yaml
transport:
  servers: ["nats://YOUR_NATS_HOST:4222"]
  project: "game_sa"          # any name; agents must match it
  token: "CHANGE_ME_SUPER_SECRET"
```

Run it:

```bash
re-agent serve --config re-agent.orchestrator.yaml
```

## 3. Configure an agent (each volunteer)

Agents need **no Ghidra and no source tree** — just their own LLM login and the
NATS coordinates. `claude-code` (the default) uses your local `claude` CLI
subscription, so no API key is required.

```bash
re-agent init --role agent --config re-agent.agent.yaml
```

```yaml
llm:
  provider: "claude-code"     # or codex | claude | openai
  model: "claude-opus-4-8"

transport:
  servers: ["nats://YOUR_NATS_HOST:4222"]
  project: "game_sa"          # must match the orchestrator
  token: "CHANGE_ME_SUPER_SECRET"
```

Run one (or several) workers:

```bash
re-agent agent --config re-agent.agent.yaml --concurrency 2
```

Each agent pulls a function, proxies every Ghidra/source lookup back to the
orchestrator, runs its LLM reverser/checker loop, and submits the result. The
orchestrator runs parity and records progress in its session file. Leasing means
two agents never get the same function, and a crashed agent's function is
re-offered automatically after `orchestrator.job_lease_s`.

## Auth options

- **Token** (shown above) — simplest; one shared secret.
- **User/password** — distinct creds for host vs. volunteers; see the conf.
- **NKey/JWT creds** — strongest. Generate with [`nsc`](https://github.com/nats-io/nsc)
  and set `transport.creds_file: path/to/agent.creds` on each side.

## Install extras

```bash
pip install 're-agent[orchestrator]'   # host: NATS + Ghidra bridge
pip install 're-agent[agent]'          # volunteer: NATS + LLM SDKs
```
