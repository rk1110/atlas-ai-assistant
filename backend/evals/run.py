"""Eval runner: answer every golden-set question and record the results.

    docker compose exec backend python -m evals.run
    docker compose exec backend python -m evals.run --model gpt-oss-20b-cloud --notes "try 20B"
    docker compose exec backend python -m evals.run --tag acme --limit 2
    docker compose exec backend python -m evals.run --retrieval-only                  # free, ~10 s
    docker compose exec backend python -m evals.run --retrieval-only --retriever all  # compare
    docker compose exec backend python -m evals.run --retrieval-only --rewrite        # + rewriting

Per question it records the answer, latency, tokens and cost, plus:
- retrieval metrics (Phase 2): did retrieval find a document from `expected_sources`, how
  high (reciprocal rank), and did the answer cite one (evals/metrics.py);
- judge scores (Phase 3): faithfulness, answer correctness and context precision, graded by
  the cheap model (evals/judge.py). Skip them with --no-judge.
Follow-up questions are answered with their `history`, so query rewriting is measured too.

`--retrieval-only` skips the answering model and prints hit rate and MRR per question
category (keyword, follow-up, relational, ...). Use it when tuning chunking or retrieval: a
change there is measured in seconds, for free. Follow-ups are searched as typed unless
--rewrite is given (that one calls the cheap model). `--min-hit-rate` / `--min-mrr` turn it
into a CI gate: the command fails when retrieval gets worse (.github/workflows/ci.yml).

Results go to three places: Postgres (eval_runs + eval_results), a JSON report in
evals/results/ (git-ignored), and Langfuse (one trace per question, grouped as session
"eval-<run id>", tagged "eval").
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func

from api.deps import get_catalog, get_gateway, get_prompts, get_tracer, make_chat_service
from core.db import get_session_factory
from core.llm import ChatMessage, LLMError
from core.rag_config import get_rag_config
from evals.judge import Judge, JudgeScores
from evals.metrics import cited_correct, rate, reciprocal_rank
from evals.schema import GoldenQuestion, load_golden_set
from models import EvalResult, EvalRun
from retrieval import STRATEGIES, build_retriever
from services.chat_service import AnswerResult, ChatService

RESULTS_DIR = Path(__file__).parent / "results"
# Question categories (tags) reported separately. Untagged questions count as "core".
CATEGORIES = ("core", "keyword", "follow-up", "relational", "paraphrase", "multimodal")


async def run(
    chat: ChatService,
    model_id: str,
    questions: list[GoldenQuestion],
    version: int,
    notes: str | None,
    judge: Judge | None,
) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        eval_run = EvalRun(
            model_id=model_id,
            golden_set_version=version,
            notes=notes,
            retriever=chat.retriever_name,
            judge_model=judge.model_id if judge else None,
            config=_run_config(chat),
        )
        session.add(eval_run)
        await session.commit()
        run_id = eval_run.id

    judged = f" · judge {judge.model_id}" if judge else ""
    print(
        f"Eval run {run_id} · model {model_id} · retriever {chat.retriever_name}{judged}"
        f" · {len(questions)} questions\n"
    )
    rows: list[EvalResult] = []
    prompt_ref: str | None = None
    for index, q in enumerate(questions, start=1):
        result = await chat.answer(
            q.question,
            model_id,
            trace_name="eval_answer",
            session_id=f"eval-{run_id}",
            tags=["eval", f"golden-v{version}"],
            history=_history(q),
        )
        prompt_ref = result.prompt_ref
        scores = await _grade(judge, q, result)
        rows.append(_to_row(run_id, q, result, scores))
        _print_progress(index, len(questions), q, result, scores)

    summary = _summarise(rows)
    async with session_factory() as session:
        eval_run = await session.get(EvalRun, run_id)
        assert eval_run is not None
        session.add_all(rows)
        eval_run.finished_at = func.now()
        eval_run.prompt_ref = prompt_ref
        for field, value in summary.items():
            setattr(eval_run, field, value)
        await session.commit()

    report = _write_report(run_id, model_id, prompt_ref, version, notes, rows, summary)
    _print_summary(summary, rows, questions, report)
    get_tracer().flush()  # send buffered traces before the script exits
    # Non-zero exit when nothing worked, so CI can fail the build.
    return 1 if summary["error_count"] == len(rows) else 0


def _history(q: GoldenQuestion) -> list[ChatMessage]:
    return [ChatMessage(role=turn.role, content=turn.content) for turn in q.history]


def _run_config(chat: ChatService) -> dict[str, Any]:
    """The settings that produced a run, so a score can always be traced back to them."""
    config = get_rag_config()
    return {
        "strategy": chat.retriever_name,
        "top_k": config.retrieval.top_k,
        "reranker": config.reranker.model if "rerank" in chat.retriever_name else None,
        "query_rewriting": chat.rewrites_queries,
        "chunk_size": config.chunking.chunk_size,
        "embedding_model": config.embedding.model,
    }


async def _grade(
    judge: Judge | None, q: GoldenQuestion, result: AnswerResult
) -> JudgeScores | None:
    if judge is None or result.error_code:
        return None
    try:
        return await judge.grade(q.question, q.expected_answer, result.chunks, result.answer)
    except LLMError as err:  # a failed grade must not lose the answer that was just paid for
        print(f"    judge failed: {err.kind}")
        return None


def _to_row(run_id, q: GoldenQuestion, result: AnswerResult, scores: JudgeScores | None):
    c = result.completion
    retrieved = [chunk.document_id for chunk in result.chunks]
    cited = [citation.document_id for citation in result.citations]
    scored = bool(q.expected_sources)  # no expected sources = nothing to score retrieval on
    return EvalResult(
        run_id=run_id,
        question_id=q.id,
        question=q.question,
        expected_answer=q.expected_answer,
        expected_sources=q.expected_sources,
        answer=result.answer,
        error_code=result.error_code,
        latency_ms=c.latency_ms if c else None,
        time_to_first_token_ms=c.time_to_first_token_ms if c else None,
        input_tokens=c.input_tokens if c else None,
        output_tokens=c.output_tokens if c else None,
        cost_usd=Decimal(str(c.cost_usd)) if c and c.cost_usd is not None else None,
        trace_id=result.trace_id,
        retrieved_sources=retrieved,
        cited_sources=cited,
        reciprocal_rank=reciprocal_rank(retrieved, q.expected_sources) if scored else None,
        cited_correct=cited_correct(cited, q.expected_sources) if scored else None,
        search_query=result.search_query if result.search_query != q.question else None,
        faithfulness=scores.faithfulness if scores else None,
        answer_correctness=scores.answer_correctness if scores else None,
        context_precision=scores.context_precision if scores else None,
        judgement=scores.judgement.model_dump() if scores else None,
    )


def _summarise(rows: list[EvalResult]) -> dict:
    ranks = [r.reciprocal_rank for r in rows if r.reciprocal_rank is not None]
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    return {
        "question_count": len(rows),
        "error_count": sum(1 for r in rows if r.error_code),
        "avg_latency_ms": round(statistics.mean(latencies)) if latencies else None,
        "total_input_tokens": sum(r.input_tokens or 0 for r in rows),
        "total_output_tokens": sum(r.output_tokens or 0 for r in rows),
        "total_cost_usd": sum(costs, Decimal(0)) if costs else None,
        "hit_rate": rate([rank > 0 for rank in ranks]),
        "mrr": rate(ranks),
        "cited_correct_rate": rate([r.cited_correct for r in rows if r.cited_correct is not None]),
        "faithfulness": rate([r.faithfulness for r in rows if r.faithfulness is not None]),
        "answer_correctness": rate(
            [r.answer_correctness for r in rows if r.answer_correctness is not None]
        ),
        "context_precision": rate(
            [r.context_precision for r in rows if r.context_precision is not None]
        ),
    }


def _print_progress(
    index: int, total: int, q: GoldenQuestion, result: AnswerResult, scores: JudgeScores | None
) -> None:
    c = result.completion
    status = (
        f"ERROR {result.error_code}" if result.error_code else f"{c.latency_ms} ms" if c else "?"
    )
    print(f"[{index}/{total}] {q.id:32} {status}   {_retrieval_note(q, result)}")
    if result.search_query != q.question:
        print(f"    searched: {result.search_query}")
    print(f"    expected: {q.expected_answer[:110]}")
    print(f"    answer:   {' '.join(result.answer.split())[:110] or '(none)'}")
    if scores:
        faithful = "n/a" if scores.faithfulness is None else f"{scores.faithfulness:.2f}"
        print(f"    judge:    correct {scores.answer_correctness:.1f} · faithful {faithful}")
    print()


def _retrieval_note(q: GoldenQuestion, result: AnswerResult) -> str:
    if not q.expected_sources:
        return ""
    rank = reciprocal_rank([chunk.document_id for chunk in result.chunks], q.expected_sources)
    found = f"found at #{round(1 / rank)}" if rank else "NOT retrieved"
    cited = cited_correct([c.document_id for c in result.citations], q.expected_sources)
    return f"{found} · {'cited right source' if cited else 'did NOT cite it'}"


def _print_summary(
    summary: dict, rows: list[EvalResult], questions: list[GoldenQuestion], report: Path
) -> None:
    cost = summary["total_cost_usd"]
    print("Summary")
    print(f"  questions          {summary['question_count']}  (errors: {summary['error_count']})")
    print(f"  avg latency        {summary['avg_latency_ms']} ms")
    tokens_in, tokens_out = summary["total_input_tokens"], summary["total_output_tokens"]
    print(f"  tokens             {tokens_in} in / {tokens_out} out")
    print(f"  cost               {'n/a' if cost is None else f'${cost:.6f}'}")
    print(f"  hit rate @k        {_percent(summary['hit_rate'])}")
    print(f"  MRR                {summary['mrr']}")
    print(f"  cited correct      {_percent(summary['cited_correct_rate'])}")
    print(f"  answer correctness {_percent(summary['answer_correctness'])}   (judge)")
    print(f"  faithfulness       {_percent(summary['faithfulness'])}   (judge)")
    print(f"  context precision  {_percent(summary['context_precision'])}   (judge)")
    print("\n  correctness by category")
    by_id = {r.question_id: r for r in rows}
    for category in (*CATEGORIES, "unanswerable"):
        scores = [
            by_id[q.id].answer_correctness
            for q in questions
            if _category(q) == category and by_id[q.id].answer_correctness is not None
        ]
        if scores:
            print(f"    {category:13} {_percent(rate(scores)):>5}   ({len(scores)} questions)")
    print(f"  report             {report}")


def _write_report(run_id, model_id, prompt_ref, version, notes, rows, summary) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}_{str(run_id)[:8]}.json"
    fields = (
        "question_id", "question", "expected_answer", "expected_sources", "answer",
        "error_code", "latency_ms", "input_tokens", "output_tokens", "trace_id",
        "retrieved_sources", "cited_sources", "reciprocal_rank", "cited_correct",
        "search_query", "faithfulness", "answer_correctness", "context_precision", "judgement",
    )  # fmt: skip
    payload = {
        "run_id": str(run_id),
        "model_id": model_id,
        "prompt_ref": prompt_ref,
        "golden_set_version": version,
        "notes": notes,
        "summary": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in summary.items()},
        "results": [{field: getattr(r, field) for field in fields} for r in rows],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


# ---------------------------------------------------------------- retrieval only


async def run_retrieval_only(
    questions: list[GoldenQuestion],
    strategies: list[str],
    *,
    rewrite: bool,
    min_hit_rate: float | None,
    min_mrr: float | None,
) -> int:
    """Hit rate and MRR without the answering model, per strategy and question category.
    Prints only; nothing is saved. Returns 1 when a CI gate (--min-hit-rate/--min-mrr) fails
    for the FIRST strategy listed (the configured one, unless --retriever names another)."""
    chat = make_chat_service()
    scored = [q for q in questions if q.expected_sources]
    queries = {q.id: await _search_query(chat, q, rewrite) for q in scored}
    print(f"Retrieval only · {len(scored)} questions with expected sources")
    print(f"  follow-ups searched {'after rewriting' if rewrite else 'as typed (no --rewrite)'}\n")

    results: dict[str, dict[str, Any]] = {}
    for strategy in strategies:
        retriever = build_retriever(strategy)  # type: ignore[arg-type]
        ranks: dict[str, float] = {}
        started = time.perf_counter()
        for q in scored:
            chunks = await chat.retrieve(queries[q.id], retriever)
            ranks[q.id] = reciprocal_rank([c.document_id for c in chunks], q.expected_sources)
            if len(strategies) == 1:
                rank = ranks[q.id]
                position = f"#{round(1 / rank)}" if rank else "miss"
                top = chunks[0].document_id if chunks else "-"
                print(f"  {position:5} {q.id:34} top: {top}")
        elapsed_ms = (time.perf_counter() - started) * 1000 / max(len(scored), 1)
        results[strategy] = {"ranks": ranks, "ms": elapsed_ms}

    _print_comparison(scored, results)
    first = results[strategies[0]]["ranks"].values()
    hit_rate, mrr = rate([r > 0 for r in first]) or 0.0, rate(list(first)) or 0.0
    failures = []
    if min_hit_rate is not None and hit_rate < min_hit_rate:
        failures.append(f"hit rate {hit_rate:.0%} < {min_hit_rate:.0%}")
    if min_mrr is not None and mrr < min_mrr:
        failures.append(f"MRR {mrr:.3f} < {min_mrr:.3f}")
    if failures:
        print(f"\nFAIL ({strategies[0]}): {'; '.join(failures)}")
        return 1
    if min_hit_rate is not None or min_mrr is not None:
        print(f"\nPASS ({strategies[0]}): hit rate {hit_rate:.0%}, MRR {mrr:.3f}")
    return 0


async def _search_query(chat: ChatService, q: GoldenQuestion, rewrite: bool) -> str:
    if not (rewrite and q.history):
        return q.question
    query = await chat.rewrite_query(q.question, _history(q))
    print(f"  rewrote {q.id}: {query}")
    return query


def _print_comparison(scored: list[GoldenQuestion], results: dict[str, dict[str, Any]]) -> None:
    present = [c for c in CATEGORIES if any(_category(q) == c for q in scored)]
    header = f"  {'strategy':14} {'hit rate':>8} {'MRR':>6}" + "".join(
        f" {c[:10]:>10}" for c in present
    )
    print(f"\n{header} {'ms/query':>9}")
    print(f"  {'':14} {'':>8} {'':>6}" + "".join(f" {'(MRR)':>10}" for _ in present))
    for strategy, result in results.items():
        ranks: dict[str, float] = result["ranks"]
        hit_rate = rate([r > 0 for r in ranks.values()])
        mrr = rate(list(ranks.values()))
        per_category = [
            rate([ranks[q.id] for q in scored if _category(q) == category]) for category in present
        ]
        print(
            f"  {strategy:14} {_percent(hit_rate):>8} {mrr or 0:>6.3f}"
            + "".join(f" {value or 0:>10.3f}" for value in per_category)
            + f" {result['ms']:>9.0f}"
        )


def _category(q: GoldenQuestion) -> str:
    return next((t for t in q.tags if t in (*CATEGORIES, "unanswerable")), "core")


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Atlas golden-set evals.")
    parser.add_argument("--model", help="model id from config/models.yaml (default: chat model)")
    parser.add_argument("--tag", help="only questions with this tag")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--notes", help="what this run is testing, stored with the run")
    parser.add_argument(
        "--retriever",
        choices=[*STRATEGIES, "all"],
        help="retrieval strategy (default: retrieval.strategy in config/rag.yaml); "
        "'all' compares every strategy (retrieval-only)",
    )
    parser.add_argument(
        "--retrieval-only", action="store_true", help="only measure retrieval (no answering model)"
    )
    parser.add_argument(
        "--rewrite", action="store_true", help="retrieval-only: rewrite follow-ups (cheap model)"
    )
    parser.add_argument("--no-judge", action="store_true", help="skip LLM-as-judge scoring")
    parser.add_argument(
        "--no-rewrite", action="store_true", help="answer follow-ups without query rewriting"
    )
    parser.add_argument("--min-hit-rate", type=float, help="retrieval-only CI gate, e.g. 0.9")
    parser.add_argument("--min-mrr", type=float, help="retrieval-only CI gate, e.g. 0.75")
    args = parser.parse_args()

    catalog = get_catalog()
    # Answer with the CHAT model: evals measure what users get. The judge uses the cheap one.
    model_id = args.model or catalog.defaults.chat
    if catalog.get(model_id) is None:
        parser.error(f"unknown model '{model_id}'. Options: {[m.id for m in catalog.list()]}")

    golden = load_golden_set()
    questions = golden.filtered(tag=args.tag, limit=args.limit)
    if not questions:
        parser.error("no questions match those filters")

    configured = get_rag_config().retrieval.strategy
    if args.retrieval_only:
        if args.retriever == "all":
            strategies = [configured, *(s for s in STRATEGIES if s != configured)]
        else:
            strategies = [args.retriever or configured]
        raise SystemExit(
            asyncio.run(
                run_retrieval_only(
                    questions,
                    strategies,
                    rewrite=args.rewrite,
                    min_hit_rate=args.min_hit_rate,
                    min_mrr=args.min_mrr,
                )
            )
        )
    if args.retriever == "all":
        parser.error("--retriever all only works with --retrieval-only")
    retriever = build_retriever(args.retriever) if args.retriever else None
    chat = make_chat_service(retriever, rewrite=not args.no_rewrite)
    judge = None if args.no_judge else Judge(get_gateway(), get_prompts(), catalog.defaults.cheap)
    raise SystemExit(asyncio.run(run(chat, model_id, questions, golden.version, args.notes, judge)))


if __name__ == "__main__":
    main()
