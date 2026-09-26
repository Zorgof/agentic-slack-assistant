from typing import Any

import httpx
import respx

from tests.tools.conftest import days_ago
from trends_agent.tools.github_releases import API, get_framework_releases


def release(tag: str, age_days: float, **extra: Any) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "name": tag,
        "published_at": days_ago(age_days).isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
        "body": "## Highlights\n* **New** feature",
        "draft": False,
        "prerelease": False,
        **extra,
    }


@respx.mock
async def test_lists_recent_releases_skipping_old_drafts_and_prereleases(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"{API}/repos/o/r/releases").respond(
        json=[
            release("v2.0.0", 1),
            release("v2.1.0rc1", 0.5, prerelease=True),
            release("v2.1.0-draft", 0.2, draft=True),
            release("v1.0.0", 60),
        ]
    )

    out = await get_framework_releases(client, ("o/r",), 14, 3)

    assert "v2.0.0" in out
    assert "rc1" not in out and "draft" not in out and "v1.0.0" not in out
    assert "Notes: ## Highlights * **New** feature" in out


@respx.mock
async def test_prereleases_included_on_request(client: httpx.AsyncClient) -> None:
    respx.get(f"{API}/repos/o/r/releases").respond(json=[release("v3rc1", 1, prerelease=True)])
    out = await get_framework_releases(client, ("o/r",), 14, 3, include_prereleases=True)
    assert "v3rc1 (pre-release)" in out


@respx.mock
async def test_reports_quiet_invalid_and_rate_limited_repos(client: httpx.AsyncClient) -> None:
    respx.get(f"{API}/repos/o/quiet/releases").respond(json=[release("v1", 90)])
    respx.get(f"{API}/repos/o/limited/releases").respond(status_code=403)

    out = await get_framework_releases(client, ("o/quiet", "o/limited", "bad name"), 14, 3)

    assert "No releases in this period: o/quiet." in out
    assert "o/limited: GitHub rate limit reached" in out
    assert "bad name: invalid repository name" in out


@respx.mock
async def test_caps_releases_per_repo(client: httpx.AsyncClient) -> None:
    respx.get(f"{API}/repos/o/r/releases").respond(
        json=[release(f"v1.{i}", i / 10) for i in range(5)]
    )
    out = await get_framework_releases(client, ("o/r",), 14, 2)
    assert "v1.0" in out and "v1.1" in out and "v1.4" not in out
    assert "(+3 more releases in this period)" in out
