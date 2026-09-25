"""Channel-agnostic request/response types exchanged between adapters and the core."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentRequest:
    """A user message coming from any channel (Slack, CLI, ...)."""

    text: str
    # Stable id of the conversation (e.g. Slack thread) — keys the session memory.
    session_id: str
    user_id: str | None = None
    channel: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    """The final answer produced by the agents, ready to be rendered by an adapter."""

    text: str
    # Name of the agent that produced the final answer (e.g. after a handoff).
    agent_name: str
    trace_id: str
    is_error: bool = False
