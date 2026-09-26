from trends_agent.adapters.slack.formatting import (
    SECTION_LIMIT,
    build_blocks,
    markdown_to_mrkdwn,
    split_into_chunks,
)


def test_links_bold_italic_bullets_and_headings() -> None:
    markdown = (
        "## Frontier labs\n"
        "- **OpenAI** — 2026-09-22: *GPT-6* launched [source](https://openai.com/x?a=1&b=2)\n"
        "* ~~old~~ item"
    )
    assert markdown_to_mrkdwn(markdown) == (
        "*Frontier labs*\n"
        "• *OpenAI* — 2026-09-22: _GPT-6_ launched <https://openai.com/x?a=1&b=2|source>\n"
        "• ~old~ item"
    )


def test_escapes_special_characters_outside_links() -> None:
    assert markdown_to_mrkdwn("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_link_label_cannot_break_slack_link_syntax() -> None:
    assert markdown_to_mrkdwn("[a|b>c](https://x.io)") == "<https://x.io|a¦b&gt;c>"


def test_multiplication_asterisks_are_not_italic() -> None:
    assert markdown_to_mrkdwn("2*3*4 and a * b") == "2*3*4 and a * b"


def test_split_respects_limit_and_line_boundaries() -> None:
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    chunks = split_into_chunks(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "\n".join(chunks) == text


def test_split_handles_single_huge_line() -> None:
    chunks = split_into_chunks("y" * 2500, limit=1000)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


def test_build_blocks_adds_footer() -> None:
    blocks = build_blocks("Hello **world**", footer="ref `t1`")
    assert blocks[0] == {"type": "section", "text": {"type": "mrkdwn", "text": "Hello *world*"}}
    assert blocks[-1]["type"] == "context"


def test_long_answers_become_multiple_sections() -> None:
    blocks = build_blocks("\n".join("- item " + "z" * 100 for _ in range(80)))
    assert len(blocks) > 1
    assert all(len(b["text"]["text"]) <= SECTION_LIMIT for b in blocks)
