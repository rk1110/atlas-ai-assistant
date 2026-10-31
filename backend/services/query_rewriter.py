"""Query rewriting: turn a follow-up into a standalone search query before retrieval.

    user:      How many weeks of parental leave does Acme give?
    assistant: 16 weeks, fully paid, for all parents [1].
    user:      and who do I ask about it?
                 └──rewrite──▶ "Who to contact about Acme Corp parental leave"

Why: retrieval only sees the text it's given. "and who do I ask about it?" contains no word
about parental leave, so neither vector nor keyword search can find the right passage. The
chat model sees the whole conversation, but the search doesn't; rewriting closes that gap.

Cost control: it only runs when the conversation has earlier turns (a first question is
already standalone), and it uses the cheap model. If the rewrite fails, we search with the
original question: a worse search beats no answer.
"""

import logging

from core.llm import ChatMessage, LLMError, LLMGateway, TextDelta
from core.prompts import PromptRegistry
from core.tracing import Span

logger = logging.getLogger(__name__)

HISTORY_TURNS = 6  # recent messages shown to the rewriter; older ones rarely matter
TURN_MAX_CHARS = 500  # long answers are cut: the rewriter needs the topic, not every detail
QUERY_MAX_CHARS = 300


class QueryRewriter:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, model_id: str):
        self._gateway = gateway
        self._prompts = prompts
        self.model_id = model_id

    async def rewrite(
        self, question: str, history: list[ChatMessage], trace: Span | None = None
    ) -> str:
        """`history` = earlier messages, oldest first, WITHOUT the current question."""
        earlier = [m for m in history if m.role in ("user", "assistant")][-HISTORY_TURNS:]
        if not earlier:
            return question
        prompt = self._prompts.render(
            "query_rewrite",
            conversation="\n".join(
                f"{m.role}: {' '.join(m.content.split())[:TURN_MAX_CHARS]}" for m in earlier
            ),
            question=question,
        )
        parts: list[str] = []
        try:
            async for chunk in self._gateway.stream_chat(
                self.model_id,
                [ChatMessage(role="user", content=prompt.text)],
                trace=trace,
                name="rewrite_query",
                prompt_ref=prompt.ref,
            ):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
        except LLMError as err:
            logger.warning("query rewrite failed [%s], searching with the question", err.kind)
            return question
        return clean_query("".join(parts)) or question


def clean_query(text: str) -> str:
    """Models sometimes add quotes, a label or a second line despite the prompt."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    query = lines[0].removeprefix("Standalone search query:").removeprefix("Rewritten:").strip()
    return query.strip("\"'`").strip()[:QUERY_MAX_CHARS]
