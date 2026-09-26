"""Fetch a web page and extract its main text (to verify details of an announcement)."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from agents import FunctionTool, function_tool

from trends_agent.config import Settings
from trends_agent.tools.base import clamp, http_client, ttl_cached

NAME = "fetch_url"
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
_TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")


class BlockedURLError(ValueError):
    """URL is not allowed (non-HTTP scheme or private/internal address)."""


async def ensure_public_url(url: str) -> None:
    """Reject non-HTTP(S) URLs and hosts resolving to private/internal addresses (SSRF guard)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedURLError(f"Only public http(s) URLs are allowed: {url}")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise BlockedURLError(f"Cannot resolve host {parts.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise BlockedURLError(f"Refusing to fetch internal address for {parts.hostname}")


async def _download(client: httpx.AsyncClient, url: str) -> tuple[str, bytes]:
    """GET with manual redirects (each hop re-checked) and a size cap. Returns (url, body)."""
    for _ in range(MAX_REDIRECTS + 1):
        await ensure_public_url(url)
        async with client.stream("GET", url) as response:
            if response.is_redirect and "location" in response.headers:
                url = urljoin(url, response.headers["location"])
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            if content_type and content_type not in _TEXT_TYPES:
                raise ValueError(f"Unsupported content type '{content_type}' at {url}")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    break
            return url, bytes(body[:MAX_BYTES])
    raise ValueError(f"Too many redirects for {url}")


def _extract(html: bytes, url: str) -> tuple[str | None, str | None, str | None]:
    doc = trafilatura.bare_extraction(html, url=url, include_comments=False, with_metadata=True)
    if doc is None:
        return None, None, None
    if isinstance(doc, dict):
        return doc.get("title"), doc.get("date"), doc.get("text")
    return doc.title, doc.date, doc.text


async def fetch_url(client: httpx.AsyncClient, url: str, max_chars: int) -> str:
    max_chars = clamp(max_chars, 500, 20_000)
    final_url, raw = await _download(client, url)
    # trafilatura detects the encoding from bytes; parsing is CPU-bound, so off the event loop.
    title, date, text = await asyncio.to_thread(_extract, raw, final_url)
    if not text:
        return f"Fetched {final_url} but could not extract readable text."
    truncated = len(text) > max_chars
    header = [f"URL: {final_url}", f"Title: {title or '?'}", f"Date: {date or 'unknown'}"]
    body = text[:max_chars] + ("\n[… truncated]" if truncated else "")
    return "\n".join(header) + "\n\n" + body


def build(settings: Settings) -> FunctionTool:
    @ttl_cached(settings.tool_cache_ttl_seconds, maxsize=128)
    async def cached(url: str, max_chars: int) -> str:
        async with http_client(settings, follow_redirects=False) as client:
            return await fetch_url(client, url, max_chars)

    @function_tool(name_override=NAME)
    async def tool(url: str, max_chars: int = 6000) -> str:
        """Download a public web page and return its main text (title, date, body).
        Use it to read an announcement, blog post or release page and verify details.

        Args:
            url: Absolute http(s) URL.
            max_chars: Maximum characters of page text to return (500-20000).
        """
        return await cached(url.strip(), max_chars)

    return tool
