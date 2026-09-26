"""Pluggable tools available to agents.

To add a tool: create a module exposing `NAME` and `build(settings) -> Tool`,
then list it in `_TOOL_MODULES` below.
"""

from trends_agent.config import Settings
from trends_agent.core.registry import ToolRegistry
from trends_agent.tools import (
    arxiv_search,
    collect_news,
    fetch_url,
    github_releases,
    hacker_news,
    huggingface,
    provider_feeds,
    web_search,
)

_TOOL_MODULES = [
    collect_news,
    web_search,
    fetch_url,
    provider_feeds,
    github_releases,
    hacker_news,
    arxiv_search,
    huggingface,
]


def build_tool_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()
    for module in _TOOL_MODULES:
        registry.register(module.NAME, module.build(settings))
    return registry
