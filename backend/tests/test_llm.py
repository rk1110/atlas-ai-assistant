"""Gateway logic that doesn't need a real model: structured-output parsing, retry, errors.
`litellm.acompletion` is replaced with a scripted fake (monkeypatch)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from core import llm
from core.config import Settings
from core.llm import ChatMessage, LLMError, LLMGateway, _extract_json, _first_problem
from core.model_catalog import CatalogDefaults, ModelCatalog, ModelEntry
from core.tracing import Tracer


class Label(BaseModel):
    reasoning: str
    label: str


def gateway(structured_output: str = "prompt") -> LLMGateway:
    entry = ModelEntry(
        id="fake", label="Fake", provider="test", litellm_model="fake/model",
        structured_output=structured_output,
    )  # fmt: skip
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://x@y/z")  # type: ignore[call-arg]
    catalog = ModelCatalog([entry], CatalogDefaults(chat="fake", cheap="fake"), settings)
    return LLMGateway(catalog, Tracer(None, "http://x", "atlas"))


def scripted(monkeypatch, replies: list[str]) -> list[dict]:
    """Make acompletion return `replies` in order; return the list of calls it received."""
    calls: list[dict] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        content = replies[len(calls) - 1]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    return calls


@pytest.mark.parametrize(
    "raw",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here it is: {"a": 1} hope that helps'],
)
def test_extract_json_handles_fences_and_chatter(raw):
    assert _extract_json(raw) == '{"a": 1}'


def test_first_problem_names_the_field():
    with pytest.raises(ValidationError) as exc:
        Label.model_validate({"reasoning": "x"})
    assert _first_problem(exc.value).startswith("label:")


async def test_prompt_mode_puts_schema_in_system_prompt(monkeypatch):
    calls = scripted(monkeypatch, ['{"reasoning": "r", "label": "ok"}'])
    parsed, completion = await gateway().complete_structured(
        "fake",
        [ChatMessage(role="system", content="Classify."), ChatMessage(role="user", content="hi")],
        Label,
    )
    assert parsed.label == "ok" and completion.input_tokens == 7
    assert "JSON Schema" in calls[0]["messages"][0]["content"]
    assert "response_format" not in calls[0]


async def test_invalid_output_is_retried_once_with_the_error(monkeypatch):
    calls = scripted(monkeypatch, ['{"reasoning": "r"}', '{"reasoning": "r", "label": "fixed"}'])
    parsed, completion = await gateway().complete_structured(
        "fake", [ChatMessage(role="user", content="hi")], Label
    )
    assert parsed.label == "fixed"
    assert len(calls) == 2
    assert "label" in calls[1]["messages"][-1]["content"]  # the retry names the missing field
    assert completion.input_tokens == 14  # tokens summed over both attempts


async def test_gives_up_after_two_invalid_replies(monkeypatch):
    scripted(monkeypatch, ["not json", "still not json"])
    with pytest.raises(LLMError) as exc:
        await gateway().complete_structured("fake", [ChatMessage(role="user", content="hi")], Label)
    assert exc.value.kind == "invalid_output"


async def test_native_mode_sends_response_format(monkeypatch):
    calls = scripted(monkeypatch, ['{"reasoning": "r", "label": "ok"}'])
    await gateway("native").complete_structured(
        "fake", [ChatMessage(role="user", content="hi")], Label
    )
    assert calls[0]["response_format"] is Label


async def test_unknown_model_raises():
    with pytest.raises(LLMError) as exc:
        await gateway().complete_structured("nope", [], Label)
    assert exc.value.kind == "unknown_model"
