"""The Analytics API (Phase 3, v1): quality over time and usage per day, for the dashboard.

    GET /api/analytics   eval runs (scores over time) + chat usage for the last 30 days
                         + model spend from the usage ledger (Phase 7B)

Everything comes from tables we already fill: eval_runs (every `python -m evals.run`) and
messages (every chat answer records model, tokens, cost and latency). Langfuse has richer
views of the same traces; this page puts the numbers that matter next to the product.
Phase 7B adds the cost report: every model call (not just final answers) from `llm_usage`,
split by day and model, by purpose ("where does the money go?") and by user, next to the
daily budget.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Date, case, cast, func, select

from api.deps import CatalogDep, SessionDep
from core.usage import utc_midnight
from models import (
    ChunkRecord,
    Conversation,
    DocumentRecord,
    EvalRun,
    LlmUsage,
    Message,
    SemanticCacheEntry,
    User,
)

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


class CostByDay(BaseModel):
    day: date
    model_id: str
    calls: int
    cost_usd: float


class CostByPurpose(BaseModel):
    purpose: str  # the gateway call name: "chat", "classify_intent", "agent:planner", ...
    source: str  # "app", "eval", "ingestion", "script"
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostByUser(BaseModel):
    name: str  # a user's name, or the script source ("eval") for calls without a user
    calls: int
    cost_usd: float


class CostReport(BaseModel):
    daily_budget_usd: float | None
    spent_today_usd: float  # UTC day, the same window the budget cap uses
    total_usd: float  # last 30 days
    unpriced_calls: int  # calls to models with no known price (counted as $0)
    by_day: list[CostByDay]
    by_purpose: list[CostByPurpose]  # most expensive first
    by_user: list[CostByUser]  # most expensive first
    cache_entries: int  # answers saved in the semantic cache (any age)
    cache_hits: int  # questions answered from it, with no model call
    cache_saved_usd: float  # what those answers would have cost


class Analytics(BaseModel):
    totals: Totals
    eval_runs: list[EvalRunPoint]  # oldest first: the x-axis of "quality over time"
    usage: list[UsageDay]  # one row per day with at least one answer
    costs: CostReport


@router.get("")
async def analytics(session: SessionDep, catalog: CatalogDep) -> Analytics:
    return Analytics(
        totals=await _totals(session),
        eval_runs=await _eval_runs(session),
        usage=await _usage(session),
        costs=await _costs(session, catalog.budget.daily_usd),
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


async def _costs(session: SessionDep, daily_budget: float | None) -> CostReport:
    since = datetime.now().astimezone() - timedelta(days=USAGE_DAYS)
    recent = LlmUsage.created_at >= since
    cost = func.coalesce(func.sum(LlmUsage.cost_usd), 0)
    day = cast(LlmUsage.created_at, Date).label("day")

    spent_today = await session.scalar(select(cost).where(LlmUsage.created_at >= utc_midnight()))
    total, unpriced = (
        await session.execute(
            select(cost, func.count().filter(LlmUsage.cost_usd.is_(None))).where(recent)
        )
    ).one()
    by_day = await session.execute(
        select(day, LlmUsage.model_id, func.count(), cost)
        .where(recent)
        .group_by(day, LlmUsage.model_id)
        .order_by(day)
    )
    by_purpose = await session.execute(
        select(
            LlmUsage.purpose,
            LlmUsage.source,
            func.count(),
            func.sum(LlmUsage.input_tokens),
            func.sum(LlmUsage.output_tokens),
            cost,
        )
        .where(recent)
        .group_by(LlmUsage.purpose, LlmUsage.source)
        .order_by(cost.desc())
    )
    # Outer join: calls without a user (evals, ingestion) are grouped under their source.
    who = func.coalesce(User.name, LlmUsage.source)
    by_user = await session.execute(
        select(who, func.count(), cost)
        .select_from(LlmUsage)
        .outerjoin(User, User.id == LlmUsage.user_id)
        .where(recent)
        .group_by(who)
        .order_by(cost.desc())
    )
    entries, hits, saved = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(SemanticCacheEntry.hits), 0),
                func.coalesce(func.sum(SemanticCacheEntry.hits * SemanticCacheEntry.cost_usd), 0),
            )
        )
    ).one()
    return CostReport(
        cache_entries=entries or 0,
        cache_hits=int(hits or 0),
        cache_saved_usd=float(saved or 0),
        daily_budget_usd=daily_budget,
        spent_today_usd=float(spent_today or 0),
        total_usd=float(total or 0),
        unpriced_calls=unpriced or 0,
        by_day=[CostByDay(day=d, model_id=m, calls=n, cost_usd=float(c)) for d, m, n, c in by_day],
        by_purpose=[
            CostByPurpose(
                purpose=p,
                source=src,
                calls=n,
                input_tokens=tin or 0,
                output_tokens=tout or 0,
                cost_usd=float(c),
            )
            for p, src, n, tin, tout, c in by_purpose
        ],
        by_user=[CostByUser(name=w, calls=n, cost_usd=float(c)) for w, n, c in by_user],
    )


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
