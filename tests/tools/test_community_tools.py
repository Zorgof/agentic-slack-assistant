"""Hacker News, arXiv and Hugging Face tools."""

import httpx
import respx

from tests.tools.conftest import days_ago
from trends_agent.tools import arxiv_search, hacker_news, huggingface


def iso(age_days: float) -> str:
    return days_ago(age_days).isoformat().replace("+00:00", "Z")


@respx.mock
async def test_hacker_news_sorted_by_points_with_filters(client: httpx.AsyncClient) -> None:
    route = respx.get(hacker_news.API).respond(
        json={
            "hits": [
                {
                    "objectID": "1",
                    "title": "Small",
                    "url": "https://a",
                    "points": 60,
                    "num_comments": 3,
                    "created_at": iso(1),
                },
                {
                    "objectID": "2",
                    "title": "Big",
                    "url": None,
                    "points": 900,
                    "num_comments": 400,
                    "created_at": iso(2),
                },
            ]
        }
    )

    out = await hacker_news.get_hacker_news(client, "LLM", 7, 50, 10)

    assert out.index("Big") < out.index("Small")
    # Ask HN posts without url fall back to the discussion link.
    assert "Big — 900 points, 400 comments — https://news.ycombinator.com/item?id=2" in out
    params = route.calls[0].request.url.params
    assert params["query"] == "LLM" and "points>=50" in params["numericFilters"]


@respx.mock
async def test_hacker_news_empty(client: httpx.AsyncClient) -> None:
    respx.get(hacker_news.API).respond(json={"hits": []})
    assert "No Hacker News stories" in await hacker_news.get_hacker_news(client, "x", 7, 50, 5)


def test_arxiv_query_building() -> None:
    query = arxiv_search.build_query('mixture-of-experts "routing"', ("cs.CL", "cs.LG"))
    assert query == "(cat:cs.CL OR cat:cs.LG) AND (all:mixture-of-experts AND all:routing)"


@respx.mock
async def test_arxiv_filters_old_papers(client: httpx.AsyncClient) -> None:
    def entry(title: str, age: float) -> str:
        return (
            f"<entry><id>http://arxiv.org/abs/{title}</id><title>{title}</title>"
            f"<published>{iso(age)}</published><summary>Abstract of {title}</summary>"
            f"<author><name>A</name></author><author><name>B</name></author>"
            f"<author><name>C</name></author><author><name>D</name></author>"
            f'<link href="http://arxiv.org/abs/{title}" rel="alternate" type="text/html"/></entry>'
        )

    feed = (
        f'<feed xmlns="http://www.w3.org/2005/Atom">{entry("Fresh", 1)}{entry("Stale", 40)}</feed>'
    )
    respx.get(arxiv_search.API).respond(text=feed)

    out = await arxiv_search.search_arxiv(client, ("cs.CL",), "agents", 7, 5)

    assert "Fresh" in out and "Stale" not in out
    assert "A, B, C et al." in out


@respx.mock
async def test_hf_trending_with_created_filter(client: httpx.AsyncClient) -> None:
    respx.get(f"{huggingface.API}/models").respond(
        json=[
            {
                "id": "org/new",
                "likes": 10,
                "trendingScore": 50,
                "pipeline_tag": "text-generation",
                "createdAt": iso(2),
            },
            {"id": "org/old", "likes": 99, "trendingScore": 40, "createdAt": iso(300)},
        ]
    )

    out = await huggingface.get_hf_trending(client, "models", 10, 14)

    assert "org/new — text-generation, 10 likes" in out
    assert "https://huggingface.co/org/new" in out
    assert "org/old" not in out


@respx.mock
async def test_hf_spaces_links(client: httpx.AsyncClient) -> None:
    respx.get(f"{huggingface.API}/spaces").respond(
        json=[{"id": "org/demo", "likes": 1, "trendingScore": 2, "sdk": "gradio"}]
    )
    out = await huggingface.get_hf_trending(client, "spaces", 10, 0)
    assert "https://huggingface.co/spaces/org/demo" in out
