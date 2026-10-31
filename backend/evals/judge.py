"""LLM-as-judge: a (cheap) model grades each eval answer. Phase 3.

Retrieval metrics (hit rate, MRR) say whether the right *document* was found. They can't say
whether the *answer* is any good. A second model reads the question, the sources, the answer
and the expected answer, and grades three things, using the RAGAS definitions:

    faithfulness       share of the answer's claims that the sources support. Low = the
                       model made things up (hallucination), even if it sounds right.
    answer correctness does it contain the expected facts? 0, 0.5 or 1.
    context precision  were the relevant sources ranked first? (average precision over the
                       retrieved list). Low = the prompt is full of noise.

Why not the `ragas` library: it calls models through its own clients, outside our LiteLLM
gateway (principle 2: no tracing, no cost tracking there), and relies on structured output
that Ollama Cloud ignores. The metric *definitions* are what matter; these are the same ones,
computed through our gateway in a single call per question.

Judges are imperfect: they are biased toward long and confident answers, and a small judge
misses subtle errors. Use their scores to compare runs, and read the low-scoring answers.
"""

from pydantic import BaseModel, Field

from core.interfaces.retriever import Chunk
from core.llm import ChatMessage, Completion, LLMGateway
from core.prompts import PromptRegistry
from evals.metrics import average_precision
from services.grounding import format_sources


class Claim(BaseModel):
    claim: str = Field(description="One factual statement from the answer, in a few words.")
    supported: bool = Field(description="true only if the sources state or directly imply it.")


class Judgement(BaseModel):
    """Field order matters: claims and reasoning come before the score they justify."""

    claims: list[Claim] = Field(description="Every factual claim in the answer, with support.")
    relevant_sources: list[int] = Field(
        description="Numbers of the sources containing information needed for the expected answer."
    )
    correctness_reasoning: str = Field(description="One sentence: answer vs expected answer.")
    correctness: float = Field(ge=0, le=1, description="1, 0.5 or 0.")


class JudgeScores(BaseModel):
    faithfulness: float | None  # None when the answer makes no claims (e.g. "couldn't find")
    answer_correctness: float
    context_precision: float | None  # None when no source was relevant
    judgement: Judgement
    completion: Completion


class Judge:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, model_id: str):
        self._gateway = gateway
        self._prompts = prompts
        self.model_id = model_id

    async def grade(
        self, question: str, expected_answer: str, chunks: list[Chunk], answer: str
    ) -> JudgeScores:
        prompt = self._prompts.render(
            "eval_judge",
            question=question,
            expected_answer=expected_answer,
            sources=format_sources(chunks),
            answer=answer or "(no answer)",
        )
        judgement, completion = await self._gateway.complete_structured(
            self.model_id,
            [ChatMessage(role="user", content=prompt.text)],
            Judgement,
            name="eval_judge",
            prompt_ref=prompt.ref,
        )
        return score(judgement, len(chunks), completion)


def score(judgement: Judgement, source_count: int, completion: Completion) -> JudgeScores:
    claims = judgement.claims
    relevant = set(judgement.relevant_sources)
    ranked_relevance = [n in relevant for n in range(1, source_count + 1)]
    return JudgeScores(
        faithfulness=round(sum(c.supported for c in claims) / len(claims), 4) if claims else None,
        # Snap to the scale we asked for: small judges sometimes answer 0.7.
        answer_correctness=min((0.0, 0.5, 1.0), key=lambda v: abs(v - judgement.correctness)),
        context_precision=average_precision(ranked_relevance),
        judgement=judgement,
        completion=completion,
    )
