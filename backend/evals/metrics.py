"""Retrieval and citation metrics. Pure functions, so they're trivial to test and to trust.

For one question, retrieval returns a ranked list of chunks; `expected` holds the document ids
that contain the answer (any one of them counts).

    hit@k            did ANY of the top k chunks come from a right document? (yes/no)
    reciprocal rank  1 / position of the first right chunk: 1st -> 1.0, 2nd -> 0.5, 5th -> 0.2,
                     none -> 0. Averaged over questions it's MRR, which rewards putting the
                     right passage FIRST, not just somewhere in the top 5.
    cited correct    did the ANSWER cite a right document? Retrieval can find the passage and
                     the model can still ignore it or cite the wrong one; this catches that.
                     Phase 2's "done when": cited correct for >= 80% of questions.
"""

from statistics import mean


def reciprocal_rank(retrieved: list[str], expected: list[str]) -> float:
    for position, document_id in enumerate(retrieved, start=1):
        if document_id in expected:
            return 1 / position
    return 0.0


def cited_correct(cited: list[str], expected: list[str]) -> bool:
    return any(document_id in expected for document_id in cited)


def rate(values: list[float] | list[bool]) -> float | None:
    """Average of the scored questions; None when nothing was scored (no expected_sources)."""
    return round(mean(float(v) for v in values), 4) if values else None


def average_precision(relevant: list[bool]) -> float | None:
    """Context precision (RAGAS): are the relevant chunks at the TOP of the retrieved list?

    Mean of precision@k over the positions k that hold a relevant chunk. [yes, yes, no] -> 1.0;
    [no, no, yes] -> 0.33. None when nothing retrieved was relevant (nothing to rank).
    """
    hits = 0
    precisions: list[float] = []
    for k, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            hits += 1
            precisions.append(hits / k)
    return round(mean(precisions), 4) if precisions else None
