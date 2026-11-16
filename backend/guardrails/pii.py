"""PII masking (Phase 7): personal data in a user's message is replaced before any model,
log, trace or database row sees it.

    "Call me on +31 6 1234 5678" -> "Call me on <PHONE_NUMBER>"

Presidio (Microsoft, open source) finds the entities: regexes with checksums for structured
ones (credit cards, IBANs), the `phonenumbers` library for phone numbers, and a spaCy NER
model (named-entity recognition: a small neural network that tags words as names, places...)
for context. Each match has a confidence score; `min_score` drops weak ones.

Why mask instead of block: the question usually still makes sense without the number
("my phone <PHONE_NUMBER> doesn't get 2FA codes"), and the user is told what was masked.
"""

import logging
import threading
from collections import Counter
from functools import lru_cache
from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel

from core.guardrails_config import PiiConfig, get_guardrails_config

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine, RecognizerResult

logger = logging.getLogger(__name__)

SPACY_MODEL = "en_core_web_sm"  # 12 MB; Presidio's default (_lg, 560 MB) is overkill here

# (singular, plural) for the message the user sees.
LABELS = {
    "EMAIL_ADDRESS": ("email address", "email addresses"),
    "PHONE_NUMBER": ("phone number", "phone numbers"),
    "CREDIT_CARD": ("card number", "card numbers"),
    "IBAN_CODE": ("bank account (IBAN)", "bank accounts (IBAN)"),
    "US_SSN": ("social security number", "social security numbers"),
    "IP_ADDRESS": ("IP address", "IP addresses"),
    "PERSON": ("name", "names"),
    "LOCATION": ("place", "places"),
}


class MaskResult(BaseModel):
    text: str
    found: dict[str, int]  # entity type -> how many were masked

    def summary(self) -> str:
        """'1 phone number, 2 email addresses'."""
        parts = []
        for entity, count in self.found.items():
            one, many = LABELS.get(entity, (entity.lower(), entity.lower()))
            parts.append(f"{count} {one if count == 1 else many}")
        return ", ".join(parts)


class PiiMasker:
    def __init__(self, config: PiiConfig):
        self._config = config
        self._engine: AnalyzerEngine | None = None
        self._lock = threading.Lock()

    @property
    def engine(self) -> "AnalyzerEngine":
        """Loaded on first use (spaCy takes a second or two)."""
        with self._lock:
            if self._engine is None:
                from presidio_analyzer import AnalyzerEngine
                from presidio_analyzer.nlp_engine import NlpEngineProvider

                provider = NlpEngineProvider(
                    nlp_configuration={
                        "nlp_engine_name": "spacy",
                        "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
                    }
                )
                self._engine = AnalyzerEngine(nlp_engine=provider.create_engine())
        return self._engine

    async def mask(self, text: str) -> MaskResult:
        if not self._config.enabled or not text.strip():
            return MaskResult(text=text, found={})
        return await anyio.to_thread.run_sync(self._mask, text)

    def _mask(self, text: str) -> MaskResult:
        results = self.engine.analyze(
            text=text,
            language="en",
            entities=self._config.entities,
            score_threshold=self._config.min_score,
        )
        kept = _without_overlaps([r for r in results if not self._allowed(text, r)])
        # Replace from the end, so earlier offsets stay valid.
        masked = text
        for r in sorted(kept, key=lambda r: r.start, reverse=True):
            masked = masked[: r.start] + f"<{r.entity_type}>" + masked[r.end :]
        found = dict(Counter(r.entity_type for r in sorted(kept, key=lambda r: r.start)))
        if found:
            logger.info("masked PII in a message: %s", found)  # types only, never the values
        return MaskResult(text=masked, found=found)

    def _allowed(self, text: str, result: "RecognizerResult") -> bool:
        if result.entity_type != "EMAIL_ADDRESS":
            return False
        domain = text[result.start : result.end].rsplit("@", 1)[-1].lower()
        return any(
            domain == d or domain.endswith("." + d) for d in self._config.allow_email_domains
        )


def _without_overlaps(results: list["RecognizerResult"]) -> list["RecognizerResult"]:
    """Two recognizers can match the same span (an email also looks like a URL); keep the
    higher-scoring one."""
    kept: list[RecognizerResult] = []
    for r in sorted(results, key=lambda r: (-r.score, r.start)):
        if all(r.end <= k.start or r.start >= k.end for k in kept):
            kept.append(r)
    return kept


@lru_cache
def get_pii_masker() -> PiiMasker:
    return PiiMasker(get_guardrails_config().pii)
