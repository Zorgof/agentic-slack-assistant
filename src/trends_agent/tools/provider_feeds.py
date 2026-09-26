"""Latest posts from frontier AI labs' official blogs/news feeds (RSS/Atom)."""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime

import feedparser
import httpx
import structlog
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.sources import Provider, Sources, load_sources
from trends_agent.tools.base import (
    clamp,
    cutoff,
    from_struct_time,
    http_client,
    plain_text,
    ttl_cached,
)

NAME = "get_provider_updates"

log = structlog.get_logger(__name__)

_ANNOUNCEMENT_WORDS = re.compile(
    r"\b(introduc\w*|announc\w*|launch\w*|releas\w*|now available|unveil\w*|new model)\b",
    re.IGNORECASE,
)
_ANNOUNCEMENT_CATEGORIES = {"product", "research", "release", "publication", "models"}


@dataclass(frozen=True)
class FeedItem:
    provider: str
    published: datetime
    title: str
    link: str
    summary: str
    categories: tuple[str, ...] = ()


def is_announcement(item: "FeedItem") -> bool:
    """Heuristic: launches/releases rank above customer stories and policy posts."""
    if _ANNOUNCEMENT_CATEGORIES.intersection(c.lower() for c in item.categories):
        return True
    return bool(_ANNOUNCEMENT_WORDS.search(item.title))


async def _read_feed(client: httpx.AsyncClient, provider: Provider, url: str) -> list[FeedItem]:
    response = await client.get(url)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    excluded = {c.lower() for c in provider.exclude_categories}
    items = []
    for entry in parsed.entries:
        published = from_struct_time(entry.get("published_parsed") or entry.get("updated_parsed"))
        categories = tuple(t.get("term", "") for t in entry.get("tags", []) if t.get("term"))
        if published is None or excluded.intersection(c.lower() for c in categories):
            continue
        items.append(
            FeedItem(
                provider=provider.name,
                published=published,
                title=plain_text(entry.get("title"), 200),
                link=entry.get("link", ""),
                summary=plain_text(entry.get("summary"), 250),
                categories=categories,
            )
        )
    return items


async def get_provider_updates(
    client: httpx.AsyncClient,
    sources: Sources,
    providers: tuple[str, ...],
    since_days: int,
    max_items_per_provider: int,
) -> str:
    since_days = clamp(since_days, 1, 90)
    max_items_per_provider = clamp(max_items_per_provider, 1, 20)
    notes: list[str] = []

    selected: list[Provider] = []
    for name in providers:
        found = sources.find_provider(name)
        if found:
            selected.append(found)
        else:
            known = ", ".join(p.name for p in sources.providers)
            notes.append(f"Unknown provider '{name}'. Known providers: {known}.")
    if not providers:
        selected = list(sources.providers)

    with_feeds = [p for p in selected if p.feeds]
    feedless = [p for p in selected if not p.feeds]
    if feedless:
        names = ", ".join(p.name for p in feedless)
        sites = " OR ".join(f"site:{p.site}" for p in feedless)
        notes.append(
            f"No RSS feed for: {names}. Check them with web_search, e.g. one query "
            f"'new model release {sites}'."
        )

    jobs = [(p, url) for p in with_feeds for url in p.feeds]
    results = await asyncio.gather(
        *(_read_feed(client, p, url) for p, url in jobs), return_exceptions=True
    )

    since = cutoff(since_days)
    by_provider: dict[str, list[FeedItem]] = {p.name: [] for p in with_feeds}
    for (provider, url), result in zip(jobs, results, strict=True):
        name = provider.name
        if isinstance(result, BaseException):
            log.warning("feed_failed", provider=name, url=url, error=str(result))
            notes.append(f"{name}: feed {url} could not be read ({type(result).__name__}).")
            continue
        by_provider[name].extend(item for item in result if item.published >= since)

    lines = [f"Official lab posts from the last {since_days} days (announcements first):"]
    for name, items in by_provider.items():
        unique = {item.link: item for item in items}.values()
        by_date = sorted(unique, key=lambda i: i.published, reverse=True)
        # Stable sort: announcements first, each group still newest-first.
        newest = sorted(by_date, key=lambda i: not is_announcement(i))[:max_items_per_provider]
        if not newest:
            lines.append(f"\n{name}: no posts in this period.")
            continue
        lines.append(f"\n{name}:")
        for item in newest:
            category = f" ({', '.join(item.categories)})" if item.categories else ""
            day = item.published.date().isoformat()
            lines.append(f"- [{day}]{category} {item.title} — {item.link}")
            if item.summary:
                lines.append(f"  {item.summary}")
    if notes:
        lines.append("\nNotes:")
        lines.extend(f"- {n}" for n in notes)
    return "\n".join(lines)


def build(settings: Settings) -> FunctionTool:
    sources = load_sources(settings.sources_path)

    @ttl_cached(settings.tool_cache_ttl_seconds)
    async def cached(providers: tuple[str, ...], since_days: int, max_items: int) -> str:
        async with http_client(settings) as client:
            return await get_provider_updates(client, sources, providers, since_days, max_items)

    @function_tool(name_override=NAME)
    async def tool(
        providers: list[str] | None = None, since_days: int = 7, max_items_per_provider: int = 10
    ) -> str:
        """Latest posts from official blogs/news feeds of frontier AI labs (OpenAI, Google
        DeepMind, Microsoft, NVIDIA, Hugging Face, ...). Labs without a feed are listed with the
        site to search instead. Primary source for new model announcements.

        Args:
            providers: Lab names to include, e.g. ["OpenAI", "Google DeepMind"]. Omit for all.
            since_days: Only posts published within this many days (1-90).
            max_items_per_provider: Maximum posts returned per lab (1-20).
        """
        names = tuple(sorted(providers or ()))
        return await cached(names, since_days, max_items_per_provider)

    return tool
