"""Prompt registry: loads versioned prompt templates from `prompts/*.yaml`.

Why prompts live in versioned files instead of Python strings:
- A prompt is a behaviour-defining artifact, like code. Changing one word can change answer
  quality, so every change should be reviewable (git diff) and measurable (evals).
- Each saved message and trace records `name@version`, so when an answer looks wrong you can
  see exactly which prompt produced it, and compare versions with the eval suite.
- Non-engineers can tune prompts without touching Python.

Alternatives: Langfuse's built-in prompt management (edit prompts in a UI, fetched at runtime)
is a valid next step; we start with files because they are simpler, offline and in git.
"""

from datetime import date
from pathlib import Path
from string import Template

import yaml
from pydantic import BaseModel, Field, model_validator


class PromptVersion(BaseModel):
    template: str
    variables: list[str] = Field(default_factory=list)
    created: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def variables_match_template(self) -> "PromptVersion":
        """Catch drift between the declared variables and the $placeholders actually used."""
        used = set(Template(self.template).get_identifiers())
        declared = set(self.variables)
        if used != declared:
            raise ValueError(f"template uses {sorted(used)} but declares {sorted(declared)}")
        return self


class PromptFile(BaseModel):
    """The shape of one prompts/<name>.yaml file."""

    name: str
    description: str = ""
    active: str
    versions: dict[str, PromptVersion]

    @model_validator(mode="after")
    def active_version_exists(self) -> "PromptFile":
        if self.active not in self.versions:
            raise ValueError(f"active version '{self.active}' not in {sorted(self.versions)}")
        return self


class RenderedPrompt(BaseModel):
    """A filled-in prompt plus its identity, so callers can record which prompt they used."""

    name: str
    version: str
    text: str

    @property
    def ref(self) -> str:
        """Short id for logs, traces and the database, e.g. 'chat_system@v1'."""
        return f"{self.name}@{self.version}"


class PromptNotFoundError(KeyError):
    pass


class PromptRegistry:
    def __init__(self, prompts: dict[str, PromptFile]):
        self._prompts = prompts

    @classmethod
    def from_directory(cls, directory: Path) -> "PromptRegistry":
        """Load and validate every *.yaml file at startup: a broken prompt fails fast."""
        prompts: dict[str, PromptFile] = {}
        for path in sorted(directory.glob("*.yaml")):
            prompt = PromptFile.model_validate(yaml.safe_load(path.read_text()))
            if prompt.name != path.stem:
                raise ValueError(f"{path.name}: name '{prompt.name}' must match the file name")
            prompts[prompt.name] = prompt
        return cls(prompts)

    def names(self) -> list[str]:
        return sorted(self._prompts)

    def render(self, name: str, version: str | None = None, **variables: str) -> RenderedPrompt:
        """Fill in a prompt. `version=None` means the file's `active` version; pass a version
        explicitly to pin one (e.g. evals comparing v1 against v2)."""
        prompt = self._prompts.get(name)
        if prompt is None:
            raise PromptNotFoundError(name)
        chosen = version or prompt.active
        if chosen not in prompt.versions:
            raise PromptNotFoundError(f"{name}@{chosen}")
        spec = prompt.versions[chosen]

        missing = set(spec.variables) - set(variables)
        extra = set(variables) - set(spec.variables)
        if missing or extra:
            raise ValueError(
                f"{name}@{chosen}: missing {sorted(missing)}, unexpected {sorted(extra)}"
            )

        text = Template(spec.template).substitute(variables)
        return RenderedPrompt(name=name, version=chosen, text=text)
