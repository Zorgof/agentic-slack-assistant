"""Channel-agnostic cleanup of the final agent answer."""

import re

# Hosted web search appends its own citation after the model's link, e.g.
# "[source](https://x.com/a) ([x.com](https://x.com/a?utm_source=openai))".
_AUTO_CITATION = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)\s]+\)\)")
_UTM_PARAM = re.compile(r"[?&]utm_source=openai(?=[)&#\s]|$)")


def clean_answer(text: str) -> str:
    text = _AUTO_CITATION.sub("", text)
    return _UTM_PARAM.sub("", text).strip()
