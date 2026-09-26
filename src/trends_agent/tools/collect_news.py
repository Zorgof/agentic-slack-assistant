"""One-call AI news digest: every tracked source is checked, in parallel, by code.

This is a deterministic "collect" step (a fixed workflow) in front of the LLM: the agent no
longer decides *which* labs to check — it only filters and summarizes what was collected.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import structlog
from agents import FunctionTool, function_tool
from openai import AsyncOpenAI

from trends_agent.config import Settings
from trends_agent.sources import Sources, load_sources
from trends_agent.tools.base import clamp, http_client, ttl_cached
from trends_agent.tools.github_releases import get_framework_releases, github_client
from trends_agent.tools.huggingface import get_hf_trending
from trends_agent.tools.lab_search import search_lab_news
from trends_agent.tools.provider_feeds import get_provider_updates

NAME = "collect_ai_news"

log = structlog.get_logger(__name__)


def _section(result: str | BaseException, what: str) -> str:
    if isinstance(result, BaseException):
        log.warning("collect_section_failed", section=what, error=str(result))
        return f"(Could not collect {what}: {type(result).__name__}: {result})"
    return result


async def collect_ai_news(
    http: httpx.AsyncClient,
    github: httpx.AsyncClient,
    openai_client: AsyncOpenAI,
    search_model: str,
    sources: Sources,
    since_days: int,
) -> str:
    since_days = clamp(since_days, 1, 31)
    today = datetime.now(UTC).date()
    feed_labs = tuple(p.name for p in sources.providers if p.feeds)
    searched_labs = [p for p in sources.providers if not p.feeds]

    feeds, releases, trending, *searches = await asyncio.gather(
        get_provider_updates(http, sources, feed_labs, since_days, 10),
        get_framework_releases(github, tuple(sources.framework_repos), since_days, 2),
        get_hf_trending(http, "models", 10, max(since_days, 14)),
        *(
            search_lab_news(openai_client, search_model, p, since_days, today)
            for p in searched_labs
        ),
        return_exceptions=True,
    )

    lab_names = ", ".join(p.name for p in sources.providers)
    parts = [
        f"AI NEWS DIGEST — last {since_days} days (up to {today.isoformat()}).",
        f"Tracked labs (report on EVERY one of them): {lab_names}.",
        "\n== FRONTIER LABS: official feeds ==",
        _section(feeds, "lab feeds"),
        "\n== FRONTIER LABS: web search (labs without a feed) ==",
    ]
    for provider, result in zip(searched_labs, searches, strict=True):
        parts.append(f"\n{provider.name}:")
        parts.append(_section(result, f"{provider.name} news"))
    parts += [
        "\n== FRAMEWORK RELEASES (GitHub) ==",
        _section(releases, "framework releases"),
        "\n== TRENDING NEW OPEN-WEIGHT MODELS (Hugging Face) ==",
        _section(trending, "Hugging Face trending"),
    ]
    return "\n".join(parts)


def build(settings: Settings) -> FunctionTool:
    sources = load_sources(settings.sources_path)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

    @ttl_cached(settings.tool_cache_ttl_seconds, maxsize=32)
    async def cached(since_days: int) -> str:
        async with http_client(settings) as http, github_client(settings) as github:
            return await collect_ai_news(
                http, github, openai_client, settings.openai_model_search, sources, since_days
            )

    @function_tool(name_override=NAME)
    async def tool(since_days: int = 14) -> str:
        """Collect ALL tracked AI news in one call: official feeds of frontier labs, a web
        search for each lab without a feed, GitHub releases of agent/LLM frameworks and
        trending new open-weight models. Use it first for broad "what's new" questions.

        Args:
            since_days: Period to cover, in days (1-31).
        """
        return await cached(since_days)

    return tool
