"""Per-lab news search for labs without an RSS feed.

Calls the OpenAI Responses API with hosted web search directly from code (not via the agent),
so every tracked lab is always checked — coverage no longer depends on the model's choices.
"""

from datetime import date, timedelta

from openai import AsyncOpenAI

from trends_agent.sources import Provider

MAX_OUTPUT_CHARS = 1500

PROMPT = """\
Today is {today}. Find announcements published by {lab} between {start} and {today} \
(inclusive): new AI models, model versions, major products or API features.
Search the official site {site} first, then reputable tech news.
Reply ONLY with lines in this exact format, newest first, at most 6 lines:
- [YYYY-MM-DD] <what was announced> — <official URL if available, else news URL>
Only include items whose publication date you verified falls in the range. \
If there are none, reply exactly: NONE"""


async def search_lab_news(
    client: AsyncOpenAI, model: str, provider: Provider, since_days: int, today: date
) -> str:
    """Return dated announcement lines for one lab, or a 'none found' sentence."""
    prompt = PROMPT.format(
        lab=provider.name,
        site=provider.site,
        today=today.isoformat(),
        start=(today - timedelta(days=since_days)).isoformat(),
    )
    response = await client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "web_search", "search_context_size": "medium"}],
        reasoning={"effort": "low"},
    )
    text = response.output_text.strip()
    if not text or text.upper().startswith("NONE"):
        return "No announcements found in this period."
    return text[:MAX_OUTPUT_CHARS]
