"""Convert agent Markdown to Slack mrkdwn and Block Kit blocks.

Slack's mrkdwn differs from Markdown: *bold* (single asterisks), _italic_, <url|text> links,
no headings, and &, <, > must be escaped.
"""

import re
from typing import Any

# Slack limits: 3000 chars per section block text, 50 blocks per message.
SECTION_LIMIT = 2900
MAX_BLOCKS = 48
FALLBACK_LIMIT = 3000

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_STRIKE = re.compile(r"~~(.+?)~~")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE)
_BOLD_MARK = "\x01"
_LINK_MARK = "\x02{}\x02"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_mrkdwn(markdown: str) -> str:
    links: list[str] = []

    def stash_link(match: re.Match[str]) -> str:
        label = _escape(match.group(1)).replace("|", "¦")
        links.append(f"<{match.group(2)}|{label}>")
        return _LINK_MARK.format(len(links) - 1)

    text = _LINK.sub(stash_link, markdown)
    text = _escape(text)
    text = _HEADING.sub(lambda m: f"{_BOLD_MARK}{m.group(1)}{_BOLD_MARK}", text)
    text = _BULLET.sub(lambda m: f"{m.group(1)}• ", text)
    text = _BOLD.sub(lambda m: f"{_BOLD_MARK}{m.group(1) or m.group(2)}{_BOLD_MARK}", text)
    text = _ITALIC.sub(r"_\1_", text)
    text = _STRIKE.sub(r"~\1~", text)
    text = text.replace(_BOLD_MARK, "*")
    for index, link in enumerate(links):
        text = text.replace(_LINK_MARK.format(index), link)
    return text


def split_into_chunks(text: str, limit: int = SECTION_LIMIT) -> list[str]:
    """Split on line boundaries so each chunk fits into one section block."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single very long line
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return chunks


def build_blocks(markdown: str, footer: str | None = None) -> list[dict[str, Any]]:
    mrkdwn = markdown_to_mrkdwn(markdown)
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
        for chunk in split_into_chunks(mrkdwn)
    ][:MAX_BLOCKS]
    if footer:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    return blocks


def fallback_text(markdown: str) -> str:
    """Plain text used for notifications and clients that can't render blocks."""
    text = markdown_to_mrkdwn(markdown)
    return text if len(text) <= FALLBACK_LIMIT else text[: FALLBACK_LIMIT - 1] + "…"
