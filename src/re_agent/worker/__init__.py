"""Pooled-agent worker: runs the reverser/checker loop against a remote backend.

A worker brings its own LLM provider and needs no Ghidra and no source tree.
It pulls jobs from the orchestrator over NATS, runs the existing
:func:`re_agent.agents.loop.run_fix_loop` with a :class:`RemoteBackend` (which
proxies every RE tool call back to the orchestrator), and submits the result.
"""
