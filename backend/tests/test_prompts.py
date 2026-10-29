"""Prompt registry: loading, validation and rendering."""

import pytest
from pydantic import ValidationError

from core.config import REPO_ROOT
from core.prompts import PromptFile, PromptNotFoundError, PromptRegistry


def registry(template: str, variables: list[str]) -> PromptRegistry:
    data = {
        "name": "t",
        "active": "v1",
        "versions": {"v1": {"template": template, "variables": variables}},
    }
    return PromptRegistry({"t": PromptFile.model_validate(data)})


def test_all_repo_prompts_load_and_render():
    reg = PromptRegistry.from_directory(REPO_ROOT / "prompts")
    assert {"chat_system", "classify_intent"} <= set(reg.names())
    rendered = reg.render("chat_system", assistant_name="Atlas", today="2026-01-01")
    assert rendered.ref.startswith("chat_system@v")  # whichever version is active
    assert "You are Atlas" in rendered.text and "2026-01-01" in rendered.text


def test_undeclared_placeholder_is_rejected_on_load():
    with pytest.raises(ValidationError, match="template uses"):
        registry("Hello $name", variables=[])


def test_missing_variable_is_rejected_on_render():
    with pytest.raises(ValueError, match="missing"):
        registry("Hello $name", variables=["name"]).render("t")


def test_literal_braces_need_no_escaping():
    text = registry('Return {"ok": true} for $who', ["who"]).render("t", who="me").text
    assert text == 'Return {"ok": true} for me'


def test_unknown_prompt_or_version():
    reg = registry("hi", [])
    with pytest.raises(PromptNotFoundError):
        reg.render("nope")
    with pytest.raises(PromptNotFoundError):
        reg.render("t", version="v9")
