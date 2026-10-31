"""The Analytics API (Phase 3, v1): quality over time and usage per day, for the dashboard.

    GET /api/analytics   eval runs (scores over time) + chat usage for the last 30 days

Everything comes from tables we already fill: eval_runs (every `python -m evals.run`) and
messages (every chat answer records model, tokens, cost and latency). Langfuse has richer
views of the same traces; this page puts the numbers that matter next to the product.
Phase 7 adds cost per user, cache hit rate and feedback.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Date, case, cast, func, select

from api.deps import SessionDep
from models import ChunkRecord, Conversation, DocumentRecord, EvalRun, Message

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

USAGE_DAYS = 30


class EvalRunPoint(BaseModel):
    id: str
    started_at: datetime
    model_id: str
    retriever: str | None
    notes: str | None
    question_count: int
    golden_set_version: int
    hit_rate: float | None
    mrr: float | None
    cited_correct_rate: float | None
    answer_correctness: float | None
    faithfulness: float | None
    context_precision: float | None
    avg_latency_ms: int | None
    total_cost_usd: float | None


class UsageDay(BaseModel):
    day: date
    answers: int
    errors: int
    avg_latency_ms: int | None
    input_tokens: int
    output_tokens: int
    cost_usd: float


class Totals(BaseModel):
    conversations: int
    answers: int
    documents: int
    chunks: int
    cost_usd: float
    avg_latency_ms: int | None


class Analytics(BaseModel):
    totals: Totals
    eval_runs: list[EvalRunPoint]  # oldest first: the x-axis of "quality over time"
    usage: list[UsageDay]  # one row per day with at least one answer


@router.get("")
async def analytics(session: SessionDep) -> Analytics:
    return Analytics(
        totals=await _totals(session),
        eval_runs=await _eval_runs(session),
        usage=await _usage(session),
    )


async def _totals(session: SessionDep) -> Totals:
    answers = Message.role == "assistant"
    conversations = await session.scalar(select(func.count()).select_from(Conversation))
    answer_count, cost, latency = (
        await session.execute(
            select(func.count(), func.sum(Message.cost_usd), func.avg(Message.latency_ms)).where(
                answers
            )
        )
    ).one()
    documents = await session.scalar(
        select(func.count()).select_from(DocumentRecord).where(DocumentRecord.status == "ready")
    )
    chunks = await session.scalar(select(func.count()).select_from(ChunkRecord))
    return Totals(
        conversations=conversations or 0,
        answers=answer_count or 0,
        documents=documents or 0,
        chunks=chunks or 0,
        cost_usd=float(cost or 0),
        avg_latency_ms=round(latency) if latency is not None else None,
    )


async def _eval_runs(session: SessionDep) -> list[EvalRunPoint]:
    runs = await session.scalars(
        select(EvalRun).where(EvalRun.finished_at.is_not(None)).order_by(EvalRun.started_at)
    )
    return [
        EvalRunPoint(
            id=str(r.id),
            started_at=r.started_at,
            model_id=r.model_id,
            retriever=r.retriever,
            notes=r.notes,
            question_count=r.question_count,
            golden_set_version=r.golden_set_version,
            hit_rate=r.hit_rate,
            mrr=r.mrr,
            cited_correct_rate=r.cited_correct_rate,
            answer_correctness=r.answer_correctness,
            faithfulness=r.faithfulness,
            context_precision=r.context_precision,
            avg_latency_ms=r.avg_latency_ms,
            total_cost_usd=_float(r.total_cost_usd),
        )
        for r in runs.all()
    ]


async def _usage(session: SessionDep) -> list[UsageDay]:
    day = cast(Message.created_at, Date).label("day")
    since = datetime.now().astimezone() - timedelta(days=USAGE_DAYS)
    rows = (
        await session.execute(
            select(
                day,
                func.count(),
                func.sum(case((Message.error_code.is_not(None), 1), else_=0)),
                func.avg(Message.latency_ms),
                func.coalesce(func.sum(Message.input_tokens), 0),
                func.coalesce(func.sum(Message.output_tokens), 0),
                func.coalesce(func.sum(Message.cost_usd), 0),
            )
            .where(Message.role == "assistant", Message.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [
        UsageDay(
            day=d,
            answers=count,
            errors=errors or 0,
            avg_latency_ms=round(latency) if latency is not None else None,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=float(cost),
        )
        for d, count, errors, latency, tokens_in, tokens_out, cost in rows
    ]


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
