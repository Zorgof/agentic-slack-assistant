"""Channel-agnostic cleanup of the final agent answer."""

import re

# Hosted web search appends its own citation after the model's link, e.g.
# "[source](https://x.com/a) ([x.com](https://x.com/a?utm_source=openai))".
_AUTO_CITATION = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)\s]+\)\)")
# Sometimes the citation *is* the link target: "[source]([x.com](https://x.com/a))".
_CITATION_AS_TARGET = re.compile(r"\]\(\[[^\]]+\]\((https?://[^)\s]+)\)\)")
# Internal citation markup the model sometimes leaks, wrapped in private-use characters:
# "\ue200cite\ue202functions.get_framework_releases\ue201".
_INTERNAL_CITATION = re.compile(r"\s*\ue200[^\ue201]*\ue201")
_UTM_PARAM = re.compile(r"[?&]utm_source=openai(?=[)&#\s]|$)")


def clean_answer(text: str) -> str:
    text = _INTERNAL_CITATION.sub("", text)
    text = _CITATION_AS_TARGET.sub(r"](\1)", text)
    text = _AUTO_CITATION.sub("", text)
    return _UTM_PARAM.sub("", text).strip()
