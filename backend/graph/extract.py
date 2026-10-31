"""Entity and relation extraction: an LLM reads a document and fills `Extraction`.

This is structured output (like intent classification in Phase 1), on a bigger schema. The
model does the reading; code does the checking: relations whose ends aren't listed entities
are dropped, so a typo in a name can't create a dangling half-edge in the graph.

Long documents are extracted section by section (split at `##`/`###` headings), merged:
one reply listing 40 people and 50 relations overflows the output limit and comes back cut
off, invalid JSON. Every section gets the document's title and owner as context, because
"Led by Elena Petrova" means nothing without knowing which team the section is about.
"""

import logging
import re

from core.llm import ChatMessage, Completion, LLMGateway
from core.prompts import PromptRegistry
from graph.schema import Extraction, entity_key

logger = logging.getLogger(__name__)

SECTION_CHARS = 1_200  # ~300 tokens of text per call: a dense org chart section yields long JSON


class GraphExtractor:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, model_id: str):
        self._gateway = gateway
        self._prompts = prompts
        self.model_id = model_id

    async def extract(
        self, title: str, text: str, owner: str | None = None
    ) -> tuple[Extraction, list[Completion]]:
        context = f"{title} (owner: {owner})" if owner else title
        merged = Extraction(entities=[], relations=[])
        completions = []
        for section in sections(text):
            prompt = self._prompts.render("graph_extract", title=context, document=section)
            extraction, completion = await self._gateway.complete_structured(
                self.model_id,
                [ChatMessage(role="user", content=prompt.text)],
                Extraction,
                name="graph_extract",
                prompt_ref=prompt.ref,
            )
            merged.entities += extraction.entities
            merged.relations += extraction.relations
            completions.append(completion)
        return clean(merged), completions


def sections(text: str, max_chars: int = SECTION_CHARS) -> list[str]:
    """Split at level-2 and -3 headings, then pack neighbouring sections up to `max_chars`."""
    parts = [p for p in re.split(r"(?m)^(?=#{2,3} )", text) if p.strip()]
    packed: list[str] = []
    for part in parts:
        if packed and len(packed[-1]) + len(part) <= max_chars:
            packed[-1] += part
        else:
            packed.append(part)
    return packed or [text]


def clean(extraction: Extraction) -> Extraction:
    """Deduplicate entities and drop relations that don't connect two listed entities."""
    entities = {entity_key(e.name): e for e in extraction.entities}
    relations = []
    seen = set()
    for r in extraction.relations:
        ends = (entity_key(r.source), entity_key(r.target))
        if ends[0] not in entities or ends[1] not in entities or ends[0] == ends[1]:
            logger.info("dropping relation with unknown or identical ends: %s", r)
            continue
        if (ends, r.type) in seen:
            continue
        seen.add((ends, r.type))
        relations.append(r)
    return Extraction(entities=list(entities.values()), relations=relations)
