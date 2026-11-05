"""The Atlas Tour (docs/tour/atlas-tour.html) quotes real files and line numbers.

Why a test: the tour is learning and handover material, and a wrong line number quietly
teaches the wrong thing. When code moves, this fails and names the reference to update.
"""

import json
import re

import pytest

from core.config import REPO_ROOT

TOUR = REPO_ROOT / "docs" / "tour" / "atlas-tour.html"
# Repo paths the tour mentions in prose, e.g. backend/core/llm.py or config/models.yaml.
PATH = re.compile(r"\b(?:backend|frontend|config|prompts)/[\w./-]+\.(?:py|ts|tsx|yaml)\b")

pytestmark = pytest.mark.skipif(not TOUR.exists(), reason="docs/ is not in this checkout")


def tour_html() -> str:
    return TOUR.read_text()


def test_every_quoted_line_still_matches():
    block = re.search(r'<script type="application/json" id="tour-refs">(.*?)</script>',
                      tour_html(), re.S)  # fmt: skip
    assert block, "the tour should list its code references in #tour-refs"
    stale = []
    for ref in json.loads(block.group(1)):
        lines = (REPO_ROOT / ref["file"]).read_text().splitlines()
        if ref["text"] not in lines[ref["line"] - 1]:
            found = [n for n, line in enumerate(lines, 1) if ref["text"] in line]
            stale.append(f"{ref['file']}:{ref['line']} {ref['text']!r} is now at {found}")
    assert not stale, "update the tour:\n" + "\n".join(stale)


def test_every_mentioned_file_exists():
    missing = sorted({p for p in PATH.findall(tour_html()) if not (REPO_ROOT / p).exists()})
    assert not missing
