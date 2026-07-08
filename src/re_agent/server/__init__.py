"""Orchestrator server: the project host's NATS responder.

Owns the Ghidra backend, source tree, parity engine, and session state.  It is a
pure responder — pooled agents make all the requests.  See
:class:`re_agent.server.service.OrchestratorService`.
"""
