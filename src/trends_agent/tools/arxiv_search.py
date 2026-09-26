"""Recent research papers from arXiv (export API, Atom feed)."""

import re

import feedparser
import httpx
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.sources import load_sources
from trends_agent.tools.base import (
    clamp,
    cutoff,
    from_struct_time,
    http_client,
    plain_text,
    ttl_cached,
)

NAME = "search_arxiv"
API = "https://export.arxiv.org/api/query"
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")


def build_query(query: str, categories: tuple[str, ...]) -> str:
    cats = " OR ".join(f"cat:{c}" for c in categories)
    words = _WORD.findall(query)
    terms = " AND ".join(f"all:{w}" for w in words)
    return f"({cats}) AND ({terms})" if terms else f"({cats})"


async def search_arxiv(
    client: httpx.AsyncClient,
    categories: tuple[str, ...],
    query: str,
    since_days: int,
    max_results: int,
) -> str:
    since_days = clamp(since_days, 1, 60)
    max_results = clamp(max_results, 1, 20)
    response = await client.get(
        API,
        params={
            "search_query": build_query(query, categories),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 50,
        },
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    since = cutoff(since_days)
    lines: list[str] = []
    for entry in feed.entries:
        published = from_struct_time(entry.get("published_parsed"))
        if published is None or published < since:
            continue
        authors = [a.get("name", "") for a in entry.get("authors", [])]
        author_text = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        lines.append(
            f"- [{published.date().isoformat()}] {plain_text(entry.get('title'), 200)} — "
            f"{author_text} — {entry.get('link')}\n  {plain_text(entry.get('summary'), 300)}"
        )
        if len(lines) >= max_results:
            break

    if not lines:
        return f"No arXiv papers matching '{query}' in the last {since_days} days."
    return f"Recent arXiv papers for '{query}' (newest first):\n" + "\n".join(lines)


def build(settings: Settings) -> FunctionTool:
    categories = tuple(load_sources(settings.sources_path).arxiv_categories)

    @ttl_cached(settings.tool_cache_ttl_seconds)
    async def cached(query: str, since_days: int, max_results: int) -> str:
        async with http_client(settings) as client:
            return await search_arxiv(client, categories, query, since_days, max_results)

    @function_tool(name_override=NAME)
    async def tool(query: str, since_days: int = 7, max_results: int = 8) -> str:
        """Search recent arXiv papers in AI categories (cs.CL, cs.LG, cs.AI), newest first.

        Args:
            query: Keywords, e.g. "reasoning model", "mixture of experts", "agent benchmark".
            since_days: Only papers submitted within this many days (1-60).
            max_results: Maximum papers returned (1-20).
        """
        return await cached(query.strip(), since_days, max_results)

    return tool
