"""Popular Hacker News stories (community signal) via the HN Algolia search API."""

import httpx
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.tools.base import clamp, cutoff, http_client, parse_iso, ttl_cached

NAME = "get_hacker_news_ai"
API = "https://hn.algolia.com/api/v1/search_by_date"


async def get_hacker_news(
    client: httpx.AsyncClient, query: str, since_days: int, min_points: int, limit: int
) -> str:
    since_days = clamp(since_days, 1, 30)
    limit = clamp(limit, 1, 25)
    since_ts = int(cutoff(since_days).timestamp())
    response = await client.get(
        API,
        params={
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{since_ts},points>={max(min_points, 0)}",
            "hitsPerPage": 100,
        },
    )
    response.raise_for_status()
    hits = sorted(response.json()["hits"], key=lambda h: h.get("points") or 0, reverse=True)

    if not hits:
        return f"No Hacker News stories matching '{query}' in the last {since_days} days."
    lines = [f"Top Hacker News stories for '{query}' (last {since_days} days, by points):"]
    for hit in hits[:limit]:
        created = parse_iso(hit.get("created_at"))
        day = created.date().isoformat() if created else "?"
        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        url = hit.get("url") or discussion
        lines.append(
            f"- [{day}] {hit.get('title')} — {hit.get('points')} points, "
            f"{hit.get('num_comments') or 0} comments — {url} (discussion: {discussion})"
        )
    return "\n".join(lines)


def build(settings: Settings) -> FunctionTool:
    @ttl_cached(settings.tool_cache_ttl_seconds)
    async def cached(query: str, since_days: int, min_points: int, limit: int) -> str:
        async with http_client(settings) as client:
            return await get_hacker_news(client, query, since_days, min_points, limit)

    @function_tool(name_override=NAME)
    async def tool(
        query: str = "LLM", since_days: int = 7, min_points: int = 50, limit: int = 10
    ) -> str:
        """Most upvoted recent Hacker News stories matching a query — shows what the developer
        community is discussing. Good for spotting trending tools, launches and debates.

        Args:
            query: Search terms, e.g. "LLM", "open source model", "agent framework", "Claude".
            since_days: Only stories posted within this many days (1-30).
            min_points: Minimum HN points to filter out noise.
            limit: Maximum stories returned (1-25).
        """
        return await cached(query.strip() or "LLM", since_days, min_points, limit)

    return tool
