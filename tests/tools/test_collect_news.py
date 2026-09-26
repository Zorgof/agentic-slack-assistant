from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import httpx
import respx
from openai import AsyncOpenAI

from tests.tools.conftest import days_ago
from trends_agent.sources import Provider, Sources
from trends_agent.tools import github_releases, huggingface
from trends_agent.tools.collect_news import collect_ai_news
from trends_agent.tools.lab_search import search_lab_news


class FakeResponses:
    """Stands in for `AsyncOpenAI().responses`; answers per lab name found in the prompt."""

    def __init__(self, answers: dict[str, str | Exception]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        for lab, answer in self.answers.items():
            if f"published by {lab} " in kwargs["input"]:
                if isinstance(answer, Exception):
                    raise answer
                return SimpleNamespace(output_text=answer)
        return SimpleNamespace(output_text="NONE")


def fake_openai(answers: dict[str, str | Exception]) -> tuple[AsyncOpenAI, FakeResponses]:
    responses = FakeResponses(answers)
    return cast(AsyncOpenAI, SimpleNamespace(responses=responses)), responses


ANTHROPIC = Provider(name="Anthropic", site="anthropic.com/news")


async def test_lab_search_prompt_and_output() -> None:
    client, responses = fake_openai({"Anthropic": "- [2026-09-22] Claude X — https://a/x\n"})

    out = await search_lab_news(client, "mini", ANTHROPIC, 14, date(2026, 9, 26))

    assert out == "- [2026-09-22] Claude X — https://a/x"
    call = responses.calls[0]
    assert call["model"] == "mini"
    assert call["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert "between 2026-09-12 and 2026-09-26" in call["input"]
    assert "anthropic.com/news" in call["input"]


async def test_lab_search_none() -> None:
    client, _ = fake_openai({"Anthropic": "NONE"})
    out = await search_lab_news(client, "mini", ANTHROPIC, 7, date(2026, 9, 26))
    assert out == "No announcements found in this period."


@respx.mock
async def test_collect_covers_every_lab_and_survives_failures(
    client: httpx.AsyncClient, sources: Sources
) -> None:
    sources.providers.append(Provider(name="xAI", site="x.ai/news"))
    respx.get("https://feeds.test/openai").respond(
        text='<rss version="2.0"><channel><item><title>Introducing GPT-X</title>'
        f"<link>https://o/x</link><pubDate>{days_ago(1).strftime('%a, %d %b %Y %H:%M:%S +0000')}"
        "</pubDate></item></channel></rss>"
    )
    respx.get(url__startswith="https://feeds.test/nvidia").respond(status_code=500)
    respx.get(f"{github_releases.API}/repos/langchain-ai/langgraph/releases").respond(
        json=[
            {
                "tag_name": "1.3.0",
                "name": "langgraph==1.3.0",
                "published_at": days_ago(2).isoformat(),
                "html_url": "https://github.com/langchain-ai/langgraph/releases/tag/1.3.0",
                "body": "New stuff",
                "draft": False,
                "prerelease": False,
            }
        ]
    )
    respx.get(f"{huggingface.API}/models").respond(status_code=503)
    openai_client, responses = fake_openai(
        {"Anthropic": "- [2026-09-22] Claude X — https://a/x", "xAI": RuntimeError("search down")}
    )

    out = await collect_ai_news(client, client, openai_client, "mini", sources, 7)

    assert "Tracked labs (report on EVERY one of them): OpenAI, Anthropic, NVIDIA, xAI." in out
    assert "Introducing GPT-X" in out
    assert "NVIDIA: feed https://feeds.test/nvidia could not be read" in out
    assert "Anthropic:\n- [2026-09-22] Claude X" in out
    assert "(Could not collect xAI news: RuntimeError: search down)" in out
    assert "langgraph==1.3.0" in out
    assert "(Could not collect Hugging Face trending" in out
    # Only labs without a feed are web-searched.
    assert len(responses.calls) == 2
