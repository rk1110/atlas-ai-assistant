"""Schema for golden_set.yaml. Loading validates it, so a typo fails before any model call."""

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class HistoryTurn(BaseModel):
    """An earlier message in the conversation, for follow-up questions (Phase 3)."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class GoldenQuestion(BaseModel):
    id: str
    question: str = Field(min_length=3)
    expected_answer: str = Field(min_length=1)
    expected_sources: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Earlier turns, oldest first. A question like "and for fathers?" only makes sense after
    # them: this is what query rewriting is measured on.
    history: list[HistoryTurn] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def kebab_case(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError(f"id '{value}' must be kebab-case, e.g. 'acme-expense-limit'")
        return value

    @field_validator("question", "expected_answer")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())  # YAML folded text keeps a trailing newline; normalise


class GoldenSet(BaseModel):
    version: int
    questions: list[GoldenQuestion]

    @model_validator(mode="after")
    def unique_ids(self) -> "GoldenSet":
        ids = [q.id for q in self.questions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate question ids: {duplicates}")
        return self

    def filtered(
        self, tag: str | None = None, limit: int | None = None, exclude_tag: str | None = None
    ) -> list[GoldenQuestion]:
        questions = [
            q
            for q in self.questions
            if (tag is None or tag in q.tags) and (exclude_tag is None or exclude_tag not in q.tags)
        ]
        return questions[:limit] if limit else questions


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> GoldenSet:
    return GoldenSet.model_validate(yaml.safe_load(path.read_text()))
