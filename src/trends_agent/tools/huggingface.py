"""Trending models/spaces on the Hugging Face Hub (open-weight model momentum)."""

from typing import Literal

import httpx
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.tools.base import clamp, cutoff, http_client, parse_iso, ttl_cached

NAME = "get_hf_trending"
API = "https://huggingface.co/api"


async def get_hf_trending(
    client: httpx.AsyncClient,
    kind: Literal["models", "spaces"],
    limit: int,
    created_within_days: int,
) -> str:
    limit = clamp(limit, 1, 30)
    response = await client.get(f"{API}/{kind}", params={"sort": "trendingScore", "limit": 100})
    response.raise_for_status()
    items = response.json()

    if created_within_days > 0:
        since = cutoff(created_within_days)
        items = [i for i in items if (c := parse_iso(i.get("createdAt"))) and c >= since]

    if not items:
        return f"No trending Hugging Face {kind} match the filter."
    base = "https://huggingface.co" + ("/spaces" if kind == "spaces" else "")
    scope = f", created in the last {created_within_days} days" if created_within_days > 0 else ""
    lines = [f"Trending Hugging Face {kind}{scope}:"]
    for item in items[:limit]:
        created = parse_iso(item.get("createdAt"))
        details = [
            item.get("pipeline_tag") or item.get("sdk"),
            f"{item.get('likes', 0)} likes",
            f"trending score {item.get('trendingScore', 0)}",
            f"created {created.date().isoformat()}" if created else None,
        ]
        text = ", ".join(d for d in details if d)
        lines.append(f"- {item['id']} — {text} — {base}/{item['id']}")
    return "\n".join(lines)


def build(settings: Settings) -> FunctionTool:
    @ttl_cached(settings.tool_cache_ttl_seconds)
    async def cached(kind: Literal["models", "spaces"], limit: int, created_days: int) -> str:
        async with http_client(settings) as client:
            return await get_hf_trending(client, kind, limit, created_days)

    @function_tool(name_override=NAME)
    async def tool(
        kind: Literal["models", "spaces"] = "models",
        limit: int = 15,
        created_within_days: int = 0,
    ) -> str:
        """Currently trending models or spaces on the Hugging Face Hub — best signal for new
        open-weight models gaining traction.

        Args:
            kind: "models" or "spaces" (demo apps).
            limit: Maximum items returned (1-30).
            created_within_days: If > 0, only items created within this many days (new releases).
        """
        return await cached(kind, limit, created_within_days)

    return tool
