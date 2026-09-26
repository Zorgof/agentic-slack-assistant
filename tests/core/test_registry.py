from typing import Any

import pytest
from agents import Agent, WebSearchTool

from trends_agent.agents import ai_trends, default_specialists, triage
from trends_agent.config import Settings
from trends_agent.core.registry import AgentRegistry, SpecialistSpec, ToolRegistry
from trends_agent.tools import build_tool_registry


def test_tool_registry_rejects_duplicates() -> None:
    registry = ToolRegistry()
    registry.register("web_search", WebSearchTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register("web_search", WebSearchTool())


def test_tool_registry_reports_unknown_tools() -> None:
    with pytest.raises(KeyError, match="nope"):
        ToolRegistry().get(["nope"])


def test_default_tool_registry_has_web_search(settings: Settings) -> None:
    assert "web_search" in build_tool_registry(settings).names()


def test_triage_hands_off_to_every_registered_specialist(settings: Settings) -> None:
    def build_other(s: Settings, t: ToolRegistry) -> Agent[Any]:
        return Agent(name="Other", instructions="x")

    specialists = default_specialists()
    specialists.register(SpecialistSpec(name="Other", description="other", build=build_other))

    agent = triage.build(settings, build_tool_registry(settings), specialists)

    assert agent.model == settings.openai_model_triage
    assert [h.name for h in agent.handoffs] == [ai_trends.NAME, "Other"]  # type: ignore[union-attr]


def test_triage_requires_a_specialist(settings: Settings) -> None:
    with pytest.raises(ValueError, match="at least one"):
        triage.build(settings, build_tool_registry(settings), AgentRegistry())


def test_research_agent_uses_research_model_and_all_tools(settings: Settings) -> None:
    agent = ai_trends.build(settings, build_tool_registry(settings))
    assert agent.model == settings.openai_model_research
    assert [t.name for t in agent.tools] == ai_trends.TOOLS
