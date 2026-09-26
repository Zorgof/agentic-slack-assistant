import httpx
import pytest
import respx

from trends_agent.tools.fetch_url import BlockedURLError, ensure_public_url, fetch_url

# IP literals avoid real DNS lookups in tests; 93.184.216.34 is a public address.
PUBLIC = "http://93.184.216.34"

ARTICLE = """<html><head><title>Model X released</title>
<meta property="article:published_time" content="2026-09-20"></head>
<body><nav>menu</nav><article><h1>Model X released</h1>
<p>Today we are releasing Model X, our most capable open-weight model so far.
It supports a 1M token context window and tool use out of the box.</p>
<p>Model X is available under the Apache 2.0 license on the Hugging Face Hub.</p>
</article></body></html>"""


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.1.2.3/",
        "http://169.254.169.254/latest",
        "ftp://x/y",
        "/rel",
    ],
)
async def test_blocks_internal_and_non_http_urls(url: str) -> None:
    with pytest.raises(BlockedURLError):
        await ensure_public_url(url)


@respx.mock
async def test_extracts_main_text_and_metadata(client: httpx.AsyncClient) -> None:
    respx.get(f"{PUBLIC}/post").respond(text=ARTICLE, headers={"content-type": "text/html"})

    out = await fetch_url(client, f"{PUBLIC}/post", 6000)

    assert "Title: Model X released" in out
    assert "Date: 2026-09-20" in out
    assert "1M token context window" in out


@respx.mock
async def test_truncates_long_pages(client: httpx.AsyncClient) -> None:
    long_article = ARTICLE.replace("</article>", "<p>" + "More details. " * 400 + "</p></article>")
    respx.get(f"{PUBLIC}/long").respond(text=long_article, headers={"content-type": "text/html"})

    out = await fetch_url(client, f"{PUBLIC}/long", 500)

    assert out.endswith("[… truncated]")


@respx.mock
async def test_redirect_to_internal_address_is_blocked(client: httpx.AsyncClient) -> None:
    respx.get(f"{PUBLIC}/go").respond(status_code=302, headers={"location": "http://127.0.0.1/"})
    with pytest.raises(BlockedURLError):
        await fetch_url(client, f"{PUBLIC}/go", 1000)


@respx.mock
async def test_follows_public_redirects(client: httpx.AsyncClient) -> None:
    respx.get(f"{PUBLIC}/old").respond(status_code=301, headers={"location": "/post"})
    respx.get(f"{PUBLIC}/post").respond(text=ARTICLE, headers={"content-type": "text/html"})
    out = await fetch_url(client, f"{PUBLIC}/old", 1000)
    assert f"URL: {PUBLIC}/post" in out


@respx.mock
async def test_rejects_binary_content(client: httpx.AsyncClient) -> None:
    respx.get(f"{PUBLIC}/paper.pdf").respond(
        content=b"%PDF", headers={"content-type": "application/pdf"}
    )
    with pytest.raises(ValueError, match="Unsupported content type"):
        await fetch_url(client, f"{PUBLIC}/paper.pdf", 1000)
