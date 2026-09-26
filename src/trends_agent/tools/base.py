"""Shared helpers for tools: HTTP client, TTL caching, date and text utilities.

Tool conventions:
- Core logic lives in a plain async function taking an `httpx.AsyncClient` (easy to test).
- `build(settings)` wraps it in a cached `function_tool` the agents can call.
- Tools return compact plain text. Partial failures (one feed down) are reported inline;
  a total failure raises, and the Agents SDK turns the exception into a message for the model.
"""

import functools
import html
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from cachetools import TTLCache

from trends_agent import __version__
from trends_agent.config import Settings

USER_AGENT = f"AITrendsScout/{__version__} (Slack AI news assistant)"


def http_client(settings: Settings, *, follow_redirects: bool = True) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=follow_redirects,
    )


def ttl_cached[**P](
    ttl_seconds: int, maxsize: int = 256
) -> Callable[[Callable[P, Awaitable[str]]], Callable[P, Awaitable[str]]]:
    """Cache results of an async function returning str. Arguments must be hashable."""

    def decorator(fn: Callable[P, Awaitable[str]]) -> Callable[P, Awaitable[str]]:
        cache: TTLCache[object, str] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
            key = (args, tuple(sorted(kwargs.items())))
            if key in cache:
                return cache[key]
            result = await fn(*args, **kwargs)
            cache[key] = result
            return result

        return wrapper

    return decorator


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def cutoff(since_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=since_days)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def from_struct_time(value: time.struct_time | None) -> datetime | None:
    """feedparser normalizes dates to UTC struct_time."""
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def plain_text(value: str | None, max_chars: int = 300) -> str:
    """Strip HTML, collapse whitespace and truncate."""
    if not value:
        return ""
    text = _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", value))).strip()
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
