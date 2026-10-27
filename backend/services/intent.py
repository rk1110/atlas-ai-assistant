"""Intent classification: the Phase 1 example of structured output.

Instead of free text, the model must answer with JSON matching `IntentClassification`.
Phase 4 uses this to route: questions go to retrieval, action requests go to the agent.

Why the field order matters: models generate left to right. Putting `reasoning` FIRST makes
the model write a one-line justification before it commits to a label, which tends to improve
accuracy (a tiny chain-of-thought), and it gives you an explanation to read when it's wrong.
"""

from typing import Literal

from pydantic import BaseModel, Field

from core.llm import ChatMessage, Completion, LLMGateway
from core.model_catalog import ModelCatalog
from core.prompts import PromptRegistry

Intent = Literal["question", "action_request", "chit_chat"]


class IntentClassification(BaseModel):
    """The schema the model must fill. Its JSON Schema (including these descriptions) is sent
    with the request, so the descriptions are instructions to the model."""

    reasoning: str = Field(description="One short sentence explaining the choice.")
    intent: Intent = Field(description="The single best-fitting intent.")
    confidence: float = Field(ge=0, le=1, description="0 = pure guess, 1 = certain.")


class IntentResult(BaseModel):
    classification: IntentClassification
    completion: Completion
    prompt_ref: str


class IntentClassifier:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, catalog: ModelCatalog):
        self._gateway = gateway
        self._prompts = prompts
        self._catalog = catalog

    async def classify(self, message: str, model_id: str | None = None) -> IntentResult:
        """Classify with the catalog's *cheap* model by default: a label doesn't need the
        strongest model, and this runs on every message once Phase 4 routes on it."""
        prompt = self._prompts.render("classify_intent")
        classification, completion = await self._gateway.complete_structured(
            model_id or self._catalog.defaults.cheap,
            [
                ChatMessage(role="system", content=prompt.text),
                ChatMessage(role="user", content=message),
            ],
            IntentClassification,
            name="classify_intent",
            prompt_ref=prompt.ref,
        )
        return IntentResult(
            classification=classification, completion=completion, prompt_ref=prompt.ref
        )
