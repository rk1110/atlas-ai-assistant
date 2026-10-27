"""Eval runner: answer every golden-set question and record the results.

    docker compose exec backend python -m evals.run
    docker compose exec backend python -m evals.run --model gpt-oss-20b-cloud --notes "try 20B"
    docker compose exec backend python -m evals.run --tag acme --limit 2

Phase 1 records answer, latency, tokens and cost per question; it does NOT score correctness
yet. Phase 2 adds retrieval metrics (did we find `expected_sources`?) and Phase 3 adds answer
scoring (LLM-as-judge, RAGAS). Recording the raw answers now gives those later metrics a
baseline to beat.

Results go to three places: Postgres (eval_runs + eval_results), a JSON report in
evals/results/ (git-ignored), and Langfuse (one trace per question, grouped as session
"eval-<run id>", tagged "eval").

This makes real model calls (cost: the selected model's price x ~5 questions).
"""

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func

from api.deps import get_catalog, get_chat_service, get_tracer
from core.db import get_session_factory
from evals.schema import GoldenQuestion, load_golden_set
from models import EvalResult, EvalRun
from services.chat_service import AnswerResult

RESULTS_DIR = Path(__file__).parent / "results"


async def run(
    model_id: str, questions: list[GoldenQuestion], version: int, notes: str | None
) -> int:
    chat = get_chat_service()
    session_factory = get_session_factory()

    async with session_factory() as session:
        eval_run = EvalRun(model_id=model_id, golden_set_version=version, notes=notes)
        session.add(eval_run)
        await session.commit()
        run_id = eval_run.id

    print(f"Eval run {run_id} · model {model_id} · {len(questions)} questions\n")
    rows: list[EvalResult] = []
    prompt_ref: str | None = None
    for index, q in enumerate(questions, start=1):
        result = await chat.answer(
            q.question,
            model_id,
            trace_name="eval_answer",
            session_id=f"eval-{run_id}",
            tags=["eval", f"golden-v{version}"],
        )
        prompt_ref = result.prompt_ref
        rows.append(_to_row(run_id, q, result))
        _print_progress(index, len(questions), q, result)

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
    _print_summary(summary, report)
    get_tracer().flush()  # send buffered traces before the script exits
    # Non-zero exit when nothing worked, so CI (Phase 3) can fail the build.
    return 1 if summary["error_count"] == len(rows) else 0


def _to_row(run_id, q: GoldenQuestion, result: AnswerResult) -> EvalResult:
    c = result.completion
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
    )


def _summarise(rows: list[EvalResult]) -> dict:
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    return {
        "question_count": len(rows),
        "error_count": sum(1 for r in rows if r.error_code),
        "avg_latency_ms": round(statistics.mean(latencies)) if latencies else None,
        "total_input_tokens": sum(r.input_tokens or 0 for r in rows),
        "total_output_tokens": sum(r.output_tokens or 0 for r in rows),
        "total_cost_usd": sum(costs, Decimal(0)) if costs else None,
    }


def _print_progress(index: int, total: int, q: GoldenQuestion, result: AnswerResult) -> None:
    c = result.completion
    status = (
        f"ERROR {result.error_code}" if result.error_code else f"{c.latency_ms} ms" if c else "?"
    )
    print(f"[{index}/{total}] {q.id:24} {status}")
    print(f"    expected: {q.expected_answer[:110]}")
    print(f"    answer:   {' '.join(result.answer.split())[:110] or '(none)'}\n")


def _print_summary(summary: dict, report: Path) -> None:
    cost = summary["total_cost_usd"]
    print("Summary")
    print(f"  questions        {summary['question_count']}  (errors: {summary['error_count']})")
    print(f"  avg latency      {summary['avg_latency_ms']} ms")
    tokens_in, tokens_out = summary["total_input_tokens"], summary["total_output_tokens"]
    print(f"  tokens           {tokens_in} in / {tokens_out} out")
    print(f"  cost             {'n/a' if cost is None else f'${cost:.6f}'}")
    print(f"  report           {report}")


def _write_report(run_id, model_id, prompt_ref, version, notes, rows, summary) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}_{str(run_id)[:8]}.json"
    payload = {
        "run_id": str(run_id),
        "model_id": model_id,
        "prompt_ref": prompt_ref,
        "golden_set_version": version,
        "notes": notes,
        "summary": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in summary.items()},
        "results": [
            {
                "question_id": r.question_id,
                "question": r.question,
                "expected_answer": r.expected_answer,
                "expected_sources": r.expected_sources,
                "answer": r.answer,
                "error_code": r.error_code,
                "latency_ms": r.latency_ms,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "trace_id": r.trace_id,
            }
            for r in rows
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Atlas golden-set evals.")
    parser.add_argument("--model", help="model id from config/models.yaml (default: chat model)")
    parser.add_argument("--tag", help="only questions with this tag")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--notes", help="what this run is testing, stored with the run")
    args = parser.parse_args()

    catalog = get_catalog()
    # Answer with the CHAT model: evals measure what users get. (The cheap model is for
    # grading answers, LLM-as-judge, in Phase 3.)
    model_id = args.model or catalog.defaults.chat
    if catalog.get(model_id) is None:
        parser.error(f"unknown model '{model_id}'. Options: {[m.id for m in catalog.list()]}")

    golden = load_golden_set()
    questions = golden.filtered(tag=args.tag, limit=args.limit)
    if not questions:
        parser.error("no questions match those filters")
    raise SystemExit(asyncio.run(run(model_id, questions, golden.version, args.notes)))


if __name__ == "__main__":
    main()
