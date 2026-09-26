import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from agents import Agent, MaxTurnsExceeded, RunContextWrapper, Runner

from trends_agent.agents import ai_trends
from trends_agent.config import Settings
from trends_agent.core.models import AgentRequest
from trends_agent.core.service import AgentService
from trends_agent.core.sessions import SessionStore

REQUEST = AgentRequest(text="What's new?", session_id="s1", channel="test")


def make_service(settings: Settings) -> AgentService:
    return AgentService(settings, Agent(name="Triage"), SessionStore(Path(":memory:")))


def patch_runner(monkeypatch: pytest.MonkeyPatch, behaviour: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_run(agent: Agent[Any], text: str, **kwargs: Any) -> Any:
        calls.append({"agent": agent, "text": text, **kwargs})
        return await behaviour()

    monkeypatch.setattr(Runner, "run", fake_run)
    return calls


async def test_success_returns_final_output_and_last_agent(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ok() -> Any:
        return SimpleNamespace(final_output="Answer", last_agent=SimpleNamespace(name="Research"))

    calls = patch_runner(monkeypatch, ok)

    response = await make_service(settings).run(REQUEST)

    assert response.text == "Answer"
    assert response.agent_name == "Research"
    assert not response.is_error
    assert calls[0]["session"].session_id == "s1"
    assert calls[0]["max_turns"] == settings.agent_max_turns
    assert calls[0]["run_config"].trace_id == response.trace_id


async def test_timeout_returns_friendly_error(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow() -> Any:
        await asyncio.sleep(5)

    patch_runner(monkeypatch, slow)

    response = await make_service(settings).run(REQUEST)

    assert response.is_error
    assert "too long" in response.text
    assert response.trace_id in response.text


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (MaxTurnsExceeded("too many"), "too many steps"),
        (
            openai.APIConnectionError(request=httpx2.Request("POST", "https://x")),
            "AI provider",
        ),
    ],
)
async def test_known_failures_return_friendly_error(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, exc: Exception, expected: str
) -> None:
    async def fail() -> Any:
        raise exc

    patch_runner(monkeypatch, fail)

    response = await make_service(settings).run(REQUEST)

    assert response.is_error
    assert expected in response.text


def test_research_instructions_contain_today_and_tracked_labs() -> None:
    agent: Agent[Any] = Agent(name="x")
    instructions = ai_trends.make_instructions(["OpenAI", "Anthropic"])
    text = instructions(RunContextWrapper(context=None), agent)
    assert datetime.now(UTC).date().isoformat() in text
    assert "Tracked frontier labs: OpenAI, Anthropic." in text
