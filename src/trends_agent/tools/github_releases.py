"""Latest GitHub releases of tracked agent/LLM frameworks (authoritative versions and dates)."""

import asyncio
import re
from typing import Any

import httpx
import structlog
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.sources import load_sources
from trends_agent.tools.base import clamp, cutoff, http_client, parse_iso, plain_text, ttl_cached

NAME = "get_framework_releases"
API = "https://api.github.com"
_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")

log = structlog.get_logger(__name__)


def github_client(settings: Settings) -> httpx.AsyncClient:
    """HTTP client with GitHub API headers; authenticated when GITHUB_TOKEN is set."""
    client = http_client(settings)
    client.headers.update(
        {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    )
    if settings.github_token:
        client.headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
    return client


async def _releases(client: httpx.AsyncClient, repo: str) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/repos/{repo}/releases", params={"per_page": 20})
    if response.status_code == 404:
        raise LookupError("repository not found or has no releases")
    if response.status_code in (403, 429):
        raise PermissionError("GitHub rate limit reached (set GITHUB_TOKEN to raise it)")
    response.raise_for_status()
    data: list[dict[str, Any]] = response.json()
    return data


async def get_framework_releases(
    client: httpx.AsyncClient,
    repos: tuple[str, ...],
    since_days: int,
    max_per_repo: int,
    include_prereleases: bool = False,
) -> str:
    since_days = clamp(since_days, 1, 180)
    max_per_repo = clamp(max_per_repo, 1, 10)
    invalid = [r for r in repos if not _REPO.match(r)]
    valid = [r for r in repos if _REPO.match(r)]

    results = await asyncio.gather(*(_releases(client, r) for r in valid), return_exceptions=True)

    since = cutoff(since_days)
    lines = [f"GitHub releases from the last {since_days} days:"]
    quiet: list[str] = []
    errors = [f"{r}: invalid repository name, expected 'owner/repo'." for r in invalid]
    for repo, result in zip(valid, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("github_releases_failed", repo=repo, error=str(result))
            errors.append(f"{repo}: {result}")
            continue
        recent = []
        for release in result:
            published = parse_iso(release.get("published_at"))
            if release.get("draft") or published is None or published < since:
                continue
            if release.get("prerelease") and not include_prereleases:
                continue
            recent.append((published, release))
        recent.sort(key=lambda pair: pair[0], reverse=True)
        if not recent:
            quiet.append(repo)
            continue
        lines.append(f"\n{repo} (https://github.com/{repo}/releases):")
        for published, release in recent[:max_per_repo]:
            tag = release.get("tag_name", "?")
            title = release.get("name") or tag
            pre = " (pre-release)" if release.get("prerelease") else ""
            lines.append(f"- [{published.date().isoformat()}] {title}{pre} — {release['html_url']}")
            notes = plain_text(release.get("body"), 400)
            if notes:
                lines.append(f"  Notes: {notes}")
        if len(recent) > max_per_repo:
            lines.append(f"  (+{len(recent) - max_per_repo} more releases in this period)")
    if quiet:
        lines.append(f"\nNo releases in this period: {', '.join(quiet)}.")
    if errors:
        lines.append("\nErrors:")
        lines.extend(f"- {e}" for e in errors)
    return "\n".join(lines)


def build(settings: Settings) -> FunctionTool:
    tracked = tuple(load_sources(settings.sources_path).framework_repos)

    @ttl_cached(settings.tool_cache_ttl_seconds)
    async def cached(
        repos: tuple[str, ...], since_days: int, max_per_repo: int, prereleases: bool
    ) -> str:
        async with github_client(settings) as client:
            return await get_framework_releases(
                client, repos, since_days, max_per_repo, prereleases
            )

    @function_tool(name_override=NAME)
    async def tool(
        repos: list[str] | None = None,
        since_days: int = 14,
        max_per_repo: int = 3,
        include_prereleases: bool = False,
    ) -> str:
        """Latest GitHub releases (version, date, release notes excerpt) of agent/LLM frameworks.
        Authoritative source for framework version numbers and release dates.
        Tracked by default: LangChain, LangGraph, LlamaIndex, OpenAI Agents SDK, CrewAI, AutoGen,
        Microsoft Agent Framework, Pydantic AI, MCP SDKs, DSPy, Haystack.

        Args:
            repos: GitHub repositories as "owner/repo". Omit for all tracked frameworks.
            since_days: Only releases published within this many days (1-180).
            max_per_repo: Maximum releases listed per repository (1-10).
            include_prereleases: Also list pre-releases (alpha/beta/rc/dev builds).
        """
        selected = tuple(repos) if repos else tracked
        return await cached(selected, since_days, max_per_repo, include_prereleases)

    return tool
