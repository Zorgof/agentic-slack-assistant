"""OpenAI hosted web search tool (runs on OpenAI's side via the Responses API)."""

from agents import WebSearchTool

from trends_agent.config import Settings

NAME = "web_search"


def build(settings: Settings) -> WebSearchTool:
    # "high" returns much more page text per result and made research runs take minutes,
    # so the default is "medium" (configurable via WEB_SEARCH_CONTEXT_SIZE).
    return WebSearchTool(search_context_size=settings.web_search_context_size)
