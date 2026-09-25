from trends_agent.core.postprocess import clean_answer


def test_removes_duplicate_hosted_citation() -> None:
    text = (
        "- Item. [source](https://github.com/a/b/releases) "
        "([github.com](https://github.com/a/b/releases?utm_source=openai))\n- Next"
    )
    assert clean_answer(text) == "- Item. [source](https://github.com/a/b/releases)\n- Next"


def test_strips_utm_param_from_remaining_links() -> None:
    assert clean_answer("[x](https://x.ai/news?utm_source=openai)") == "[x](https://x.ai/news)"


def test_keeps_other_query_params() -> None:
    text = "[x](https://x.ai/news?id=1&utm_source=openai)"
    assert clean_answer(text) == "[x](https://x.ai/news?id=1)"


def test_leaves_plain_text_untouched() -> None:
    text = "Nothing new (as of today). See [blog](https://openai.com/blog)."
    assert clean_answer(text) == text
