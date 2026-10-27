"""The golden set file is valid, and the schema catches common mistakes."""

import pytest
from pydantic import ValidationError

from evals.schema import GoldenSet, load_golden_set


def test_golden_set_file_is_valid():
    golden = load_golden_set()
    assert golden.version >= 1 and len(golden.questions) >= 5


def test_duplicate_ids_are_rejected():
    q = {"id": "same-id", "question": "Why?", "expected_answer": "Because."}
    with pytest.raises(ValidationError, match="duplicate"):
        GoldenSet.model_validate({"version": 1, "questions": [q, q]})


def test_ids_must_be_kebab_case():
    q = {"id": "Not Kebab", "question": "Why?", "expected_answer": "Because."}
    with pytest.raises(ValidationError, match="kebab-case"):
        GoldenSet.model_validate({"version": 1, "questions": [q]})


def test_filter_by_tag_and_limit():
    golden = load_golden_set()
    acme = golden.filtered(tag="acme")
    assert acme and all("acme" in q.tags for q in acme)
    assert len(golden.filtered(limit=2)) == 2
