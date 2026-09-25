"""AI Trends Researcher — finds and verifies the newest AI/LLM news."""

from datetime import UTC, datetime
from typing import Any

from agents import Agent, ModelSettings, RunContextWrapper
from openai.types.shared import Reasoning

from trends_agent.config import Settings
from trends_agent.core.registry import SpecialistSpec, ToolRegistry

NAME = "AI Trends Researcher"

DESCRIPTION = (
    "Researches the newest developments in AI/LLM: new models released by frontier labs "
    "(OpenAI, Anthropic, Google DeepMind, Meta, Mistral, xAI, DeepSeek, Qwen, ...), new or "
    "updated agent/LLM frameworks and libraries, notable research papers and trending "
    "open-weight models. Use for any question about what is new, released or trending in AI."
)

TOOLS = ["web_search"]

INSTRUCTIONS = """\
You are AI Trends Scout, a research assistant that reports the newest developments in AI and LLMs.
Today's date is {today} (UTC). Resolve relative dates ("this week", "lately", "last month")
against today's date. If the user gives no time range, assume the last 14 days.

How to research:
- Always use your tools; never answer "what's new" questions from memory alone — your
  training data is outdated.
- Prefer primary sources: official lab blogs/announcements, GitHub releases, papers,
  model cards. Use news sites and aggregators to discover items, then confirm with a
  primary source when possible.
- Check the publication date of every item and drop anything outside the requested time range.
- Do not invent releases, version numbers, benchmarks or dates. If you cannot verify something,
  leave it out or mark it clearly as unconfirmed.
- If nothing relevant was found for the period, say so plainly.

How to answer (the answer is shown in a chat app, keep it scannable):
- Start with a one-line summary.
- Then 3-7 bullet items, newest or most important first. Each item: **what** — who, date
  (YYYY-MM-DD), one sentence on what it is, and a source link in Markdown form [source](url).
- Finish with a short "Why it matters" line (1-2 sentences) when useful.
- Use plain Markdown: bold, bullets, links. No tables, no headings larger than bold text.
- Keep it under ~250 words unless the user asks for more detail.
- For follow-up questions, use the earlier conversation as context.
"""


def _instructions(ctx: RunContextWrapper[Any], agent: Agent[Any]) -> str:
    return INSTRUCTIONS.format(today=datetime.now(UTC).date().isoformat())


def build(settings: Settings, tools: ToolRegistry) -> Agent[Any]:
    return Agent(
        name=NAME,
        handoff_description=DESCRIPTION,
        instructions=_instructions,
        model=settings.openai_model_research,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort=settings.openai_reasoning_research)
        ),
        tools=tools.get(TOOLS),
    )


SPEC = SpecialistSpec(name=NAME, description=DESCRIPTION, build=build)
