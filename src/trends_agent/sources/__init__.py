"""Tracked sources (lab feeds, GitHub repos, arXiv categories) loaded from YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_SOURCES_PATH = Path(__file__).with_name("sources.yaml")


class Provider(BaseModel):
    name: str
    # Domain/path used for site-restricted web search, e.g. "anthropic.com/news".
    site: str
    feeds: list[str] = Field(default_factory=list)
    # Feed categories to skip (e.g. policy or customer-story posts that bury announcements).
    exclude_categories: list[str] = Field(default_factory=list)


class Sources(BaseModel):
    providers: list[Provider]
    framework_repos: list[str]
    arxiv_categories: list[str]

    def find_provider(self, name: str) -> Provider | None:
        wanted = name.strip().lower()
        return next((p for p in self.providers if p.name.lower() == wanted), None)


def load_sources(path: Path | None = None) -> Sources:
    with (path or DEFAULT_SOURCES_PATH).open(encoding="utf-8") as f:
        return Sources.model_validate(yaml.safe_load(f))
