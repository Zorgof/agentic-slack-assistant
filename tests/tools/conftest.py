from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from trends_agent.sources import Provider, Sources


def days_ago(days: float) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(follow_redirects=False) as c:
        yield c


@pytest.fixture
def sources() -> Sources:
    return Sources(
        providers=[
            Provider(name="OpenAI", site="openai.com/news", feeds=["https://feeds.test/openai"]),
            Provider(name="Anthropic", site="anthropic.com/news"),
            Provider(
                name="NVIDIA",
                site="blogs.nvidia.com",
                feeds=["https://feeds.test/nvidia", "https://feeds.test/nvidia-dev"],
            ),
        ],
        framework_repos=["langchain-ai/langgraph"],
        arxiv_categories=["cs.CL", "cs.LG"],
    )
