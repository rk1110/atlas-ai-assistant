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


def test_agent_tasks_load_and_matching_is_a_case_insensitive_subset():
    from evals.agent_run import ExpectedAction, _matches, load_tasks

    tasks = load_tasks()
    assert len({t.id for t in tasks}) == len(tasks) >= 10
    assert all(t.expect for t in tasks if t.route == "agent")
    proposal = {"tool": "create_ticket", "args": {"project": "it", "summary": "x"}}
    assert _matches(proposal, ExpectedAction(tool="create_ticket", args={"project": "IT"}))
    assert not _matches(proposal, ExpectedAction(tool="create_ticket", args={"project": "HR"}))
    assert not _matches(proposal, ExpectedAction(tool="post_slack_message"))
