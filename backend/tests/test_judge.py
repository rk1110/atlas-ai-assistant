"""LLM-as-judge scoring math (the model call itself is the gateway's, tested elsewhere)."""

from core.llm import Completion
from evals.judge import Claim, Judgement, score
from evals.metrics import average_precision

COMPLETION = Completion(
    model_id="cheap", litellm_model="fake", input_tokens=1, output_tokens=1, cost_usd=None,
    latency_ms=1, time_to_first_token_ms=None, finish_reason="stop",
)  # fmt: skip


def test_average_precision_rewards_relevant_sources_ranked_first():
    assert average_precision([True, True, False]) == 1.0
    assert average_precision([False, False, True]) == 0.3333
    assert average_precision([True, False, True]) == round((1 + 2 / 3) / 2, 4)
    assert average_precision([False, False]) is None


def test_score_computes_faithfulness_correctness_and_precision():
    judgement = Judgement(
        claims=[Claim(claim="16 weeks", supported=True), Claim(claim="paid", supported=False)],
        relevant_sources=[2],
        correctness_reasoning="Mostly right.",
        correctness=0.7,  # small judges drift off the scale; snapped to 0.5
    )
    scores = score(judgement, source_count=3, completion=COMPLETION)
    assert scores.faithfulness == 0.5
    assert scores.answer_correctness == 0.5
    assert scores.context_precision == 0.5  # the one relevant source was ranked 2nd


def test_no_claims_means_no_faithfulness_score():
    judgement = Judgement(
        claims=[], relevant_sources=[], correctness_reasoning="Said it couldn't find it.",
        correctness=1,
    )  # fmt: skip
    scores = score(judgement, source_count=5, completion=COMPLETION)
    assert scores.faithfulness is None and scores.context_precision is None
    assert scores.answer_correctness == 1.0
