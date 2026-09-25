"""AgentService — the single entry point adapters use to talk to the agents."""

import asyncio
from collections import defaultdict
from typing import Any

import openai
import structlog
from agents import (
    Agent,
    AgentsException,
    MaxTurnsExceeded,
    RunConfig,
    Runner,
    gen_trace_id,
    set_default_openai_key,
)

from trends_agent.agents import default_specialists, triage
from trends_agent.config import Settings
from trends_agent.core.models import AgentRequest, AgentResponse
from trends_agent.core.postprocess import clean_answer
from trends_agent.core.registry import AgentRegistry
from trends_agent.core.sessions import SessionStore
from trends_agent.tools import build_tool_registry

log = structlog.get_logger(__name__)

WORKFLOW_NAME = "AI Trends Scout"


class AgentService:
    def __init__(
        self,
        settings: Settings,
        entry_agent: Agent[Any],
        sessions: SessionStore,
    ) -> None:
        self._settings = settings
        self._entry_agent = entry_agent
        self._sessions = sessions
        # Serialize runs within one conversation so session history stays consistent.
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @classmethod
    def from_settings(
        cls, settings: Settings, specialists: AgentRegistry | None = None
    ) -> "AgentService":
        # Settings are read from .env by pydantic, not os.environ, so hand the key to the SDK.
        set_default_openai_key(settings.openai_api_key.get_secret_value())
        tools = build_tool_registry(settings)
        entry = triage.build(settings, tools, specialists or default_specialists())
        return cls(settings, entry, SessionStore(settings.session_db_path))

    async def run(self, request: AgentRequest) -> AgentResponse:
        trace_id = gen_trace_id()
        bound = log.bind(trace_id=trace_id, session_id=request.session_id, channel=request.channel)
        bound.info("agent_run_started", user_id=request.user_id)
        run_config = RunConfig(
            workflow_name=WORKFLOW_NAME,
            trace_id=trace_id,
            group_id=request.session_id,
            trace_metadata={"channel": request.channel},
        )
        try:
            async with self._locks[request.session_id]:
                result = await asyncio.wait_for(
                    Runner.run(
                        self._entry_agent,
                        request.text,
                        session=self._sessions.get(request.session_id),
                        max_turns=self._settings.agent_max_turns,
                        run_config=run_config,
                    ),
                    timeout=self._settings.agent_timeout_seconds,
                )
        except TimeoutError:
            bound.warning("agent_run_timeout")
            return self._error(
                "The research took too long and was stopped. Try a narrower question.", trace_id
            )
        except MaxTurnsExceeded:
            bound.warning("agent_run_max_turns")
            return self._error(
                "I needed too many steps to answer. Try a more specific question.", trace_id
            )
        except openai.APIError as exc:
            bound.error("openai_api_error", error=str(exc))
            return self._error(
                "The AI provider returned an error. Please try again shortly.", trace_id
            )
        except AgentsException as exc:
            bound.exception("agent_run_failed", error=str(exc))
            return self._error(
                "Something went wrong while researching. Please try again.", trace_id
            )

        agent_name = result.last_agent.name
        bound.info("agent_run_finished", agent=agent_name)
        return AgentResponse(
            text=clean_answer(str(result.final_output)), agent_name=agent_name, trace_id=trace_id
        )

    @staticmethod
    def _error(message: str, trace_id: str) -> AgentResponse:
        return AgentResponse(
            text=f"{message} (ref: `{trace_id}`)",
            agent_name="system",
            trace_id=trace_id,
            is_error=True,
        )
