"""Triage agent — entry point that routes each request to a specialist agent."""

from typing import Any

from agents import Agent, ModelSettings
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from openai.types.shared import Reasoning

from trends_agent.config import Settings
from trends_agent.core.registry import AgentRegistry, ToolRegistry

NAME = "Triage"

INSTRUCTIONS = """\
You are the front desk of AI Trends Scout, a Slack assistant.
Your only job is to route the user's message to the right specialist agent.

- If a specialist can handle the request (see their descriptions), hand off to it immediately.
  Do not answer the question yourself and do not ask clarifying questions first — the
  specialist can do that.
- Follow-up messages in an ongoing conversation go to the specialist that handled the topic.
- Greetings or "what can you do?": reply briefly (2-3 sentences) describing what the
  specialists can do, with one example question.
- Clearly unrelated requests: politely say it is outside your scope and list what you can help with.
"""


def build(settings: Settings, tools: ToolRegistry, specialists: AgentRegistry) -> Agent[Any]:
    handoffs: list[Agent[Any]] = [spec.build(settings, tools) for spec in specialists.specs()]
    if not handoffs:
        raise ValueError("Triage agent needs at least one registered specialist")
    return Agent(
        name=NAME,
        instructions=prompt_with_handoff_instructions(INSTRUCTIONS),
        model=settings.openai_model_triage,
        model_settings=ModelSettings(reasoning=Reasoning(effort=settings.openai_reasoning_triage)),
        handoffs=list(handoffs),
    )
