import contextlib
import time

from trends_agent.sources import load_sources
from trends_agent.tools.base import from_struct_time, parse_iso, plain_text, ttl_cached


async def test_ttl_cache_reuses_results_per_arguments() -> None:
    calls: list[str] = []

    @ttl_cached(ttl_seconds=60)
    async def fetch(key: str) -> str:
        calls.append(key)
        return key.upper()

    assert await fetch("a") == "A"
    assert await fetch("a") == "A"
    assert await fetch("b") == "B"
    assert calls == ["a", "b"]


async def test_ttl_cache_does_not_cache_exceptions() -> None:
    attempts = 0

    @ttl_cached(ttl_seconds=60)
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("down")
        return "ok"

    with contextlib.suppress(RuntimeError):
        await flaky()
    assert await flaky() == "ok"


def test_plain_text_strips_html_and_truncates() -> None:
    assert plain_text("<p>Hello&nbsp;<b>world</b></p>\n\n") == "Hello world"
    assert plain_text("abcdef", max_chars=4) == "abc…"
    assert plain_text(None) == ""


def test_date_parsing() -> None:
    assert parse_iso("2026-09-24T15:00:00Z").isoformat() == "2026-09-24T15:00:00+00:00"  # type: ignore[union-attr]
    assert parse_iso("garbage") is None
    parsed = from_struct_time(time.strptime("2026-09-24 10:00", "%Y-%m-%d %H:%M"))
    assert parsed is not None and parsed.tzinfo is not None


def test_bundled_sources_file_is_valid() -> None:
    sources = load_sources()
    assert sources.find_provider("openai") is not None
    assert all("/" in repo for repo in sources.framework_repos)
    assert sources.arxiv_categories
