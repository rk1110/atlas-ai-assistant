"""Markdown -> clean text that keeps its headings (the chunker splits on them).

Real-world Markdown is messy. The GitLab handbook mixes in Hugo "shortcodes" ({{< youtube >}}),
raw HTML (<div class="...">) and heading anchors ({#iteration}). None of that means anything
to an embedding model; it only adds noise that pulls vectors away from the real content.
"""

import re
from typing import Any

import yaml

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SHORTCODE = re.compile(r"\{\{[<%].*?[%>]\}\}", re.DOTALL)  # {{< x >}} and {{% x %}}
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")  # [text](url) -> text
# [ \t]* not \s*: \s also matches newlines and would swallow the blank line after a heading.
HEADING_ANCHOR = re.compile(r"^(#{1,6} .*?)[ \t]*\{#[^}]*\}[ \t]*$", re.MULTILINE)
EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


def split_front_matter(markdown: str) -> tuple[dict[str, Any], str]:
    """`---\\ntitle: X\\n---\\nbody` -> ({"title": "X"}, "body"). Bad YAML -> no metadata."""
    match = FRONT_MATTER.match(markdown)
    if not match:
        return {}, markdown
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), markdown[match.end() :]


def clean_markdown(markdown: str) -> str:
    _, text = split_front_matter(markdown)
    text = SHORTCODE.sub("", text)
    text = HTML_COMMENT.sub("", text)
    text = HTML_TAG.sub("", text)
    text = IMAGE.sub("", text)
    text = LINK.sub(r"\1", text)  # keep the words, drop the URL: URLs are noise for embeddings
    text = HEADING_ANCHOR.sub(r"\1", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return EXTRA_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
