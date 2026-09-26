"""Run hooks that log handoffs and tool calls (complements OpenAI tracing)."""

from typing import Any

import structlog
from agents import Agent, RunContextWrapper, RunHooks, Tool

log = structlog.get_logger(__name__)


class LoggingHooks(RunHooks[Any]):
    def __init__(self, trace_id: str) -> None:
        self._log = log.bind(trace_id=trace_id)

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Agent[Any], to_agent: Agent[Any]
    ) -> None:
        self._log.info("agent_handoff", from_agent=from_agent.name, to_agent=to_agent.name)

    async def on_tool_start(
        self, context: RunContextWrapper[Any], agent: Agent[Any], tool: Tool
    ) -> None:
        self._log.info("tool_started", agent=agent.name, tool=tool.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Agent[Any], tool: Tool, result: object
    ) -> None:
        self._log.debug("tool_finished", agent=agent.name, tool=tool.name, chars=len(str(result)))
