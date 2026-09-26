from email.utils import format_datetime

import httpx
import respx

from tests.tools.conftest import days_ago
from trends_agent.sources import Sources
from trends_agent.tools.provider_feeds import get_provider_updates


def rss(*items: tuple[str, str, float]) -> str:
    entries = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{format_datetime(days_ago(age))}</pubDate>"
        f"<description>&lt;p&gt;About {title}&lt;/p&gt;</description></item>"
        for title, link, age in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{entries}</channel></rss>'


@respx.mock
async def test_filters_by_date_sorts_and_notes_feedless(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    respx.get("https://feeds.test/openai").respond(
        text=rss(
            ("Old post", "https://o/old", 30),
            ("GPT-X", "https://o/x", 1),
            ("New", "https://o/n", 0.1),
        )
    )

    out = await get_provider_updates(client, sources, ("OpenAI", "Anthropic"), 7, 5)

    assert "Old post" not in out
    assert out.index("New") < out.index("GPT-X")  # newest first
    assert "About GPT-X" in out  # HTML stripped from summary
    assert "No RSS feed for: Anthropic" in out and "site:anthropic.com/news" in out


@respx.mock
async def test_one_failing_feed_does_not_break_the_rest(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    respx.get("https://feeds.test/nvidia").respond(status_code=500)
    respx.get("https://feeds.test/nvidia-dev").respond(text=rss(("CUDA news", "https://n/c", 1)))

    out = await get_provider_updates(client, sources, ("nvidia",), 7, 5)

    assert "CUDA news" in out
    assert "feeds.test/nvidia could not be read" in out


@respx.mock
async def test_unknown_provider_lists_known_ones(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    out = await get_provider_updates(client, sources, ("Nope",), 7, 5)
    assert "Unknown provider 'Nope'" in out
    assert "OpenAI, Anthropic, NVIDIA" in out


@respx.mock
async def test_limits_items_per_provider(client: httpx.AsyncClient, sources: Sources) -> None:
    respx.get("https://feeds.test/openai").respond(
        text=rss(*[(f"Post {i}", f"https://o/{i}", i / 10) for i in range(5)])
    )
    out = await get_provider_updates(client, sources, ("OpenAI",), 7, 2)
    assert out.count("- [") == 2


@respx.mock
async def test_excluded_categories_are_skipped_and_categories_shown(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    sources.providers[0].exclude_categories = ["global affairs"]
    feed = rss(("Policy talk", "https://o/p", 1), ("Introducing GPT-X", "https://o/x", 2))
    feed = feed.replace(
        "<title>Policy talk</title>",
        "<title>Policy talk</title><category>Global Affairs</category>",
    ).replace(
        "<title>Introducing GPT-X</title>",
        "<title>Introducing GPT-X</title><category>Product</category>",
    )
    respx.get("https://feeds.test/openai").respond(text=feed)

    out = await get_provider_updates(client, sources, ("OpenAI",), 7, 5)

    assert "Policy talk" not in out
    assert "(Product) Introducing GPT-X" in out


@respx.mock
async def test_announcements_rank_above_newer_stories(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    stories = [(f"Customer story {i}", f"https://o/s{i}", i / 10) for i in range(4)]
    respx.get("https://feeds.test/openai").respond(
        text=rss(*stories, ("Introducing GPT-X", "https://o/x", 3))
    )

    out = await get_provider_updates(client, sources, ("OpenAI",), 7, 2)

    assert "Introducing GPT-X" in out  # older, but survives the limit
    assert out.index("Introducing GPT-X") < out.index("Customer story 0")
