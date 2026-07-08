"""Transport layer: NATS relay plumbing shared by the orchestrator and agents.

The orchestrator (``re-agent serve``) is a pure NATS *responder*; agents
(``re-agent agent``) are *requesters*.  Both dial outbound to a NATS server, so
neither needs port forwarding.  This package holds:

- :mod:`re_agent.transport.wire` — JSON (de)serialization for the dataclasses
  that cross the wire.
- :mod:`re_agent.transport.protocol` — subject names and request/reply shapes.
- :mod:`re_agent.transport.nats_conn` — a thin async NATS client wrapper.
"""
