"""The usage ledger and the budget cap (Phase 7B): every call is recorded with its real
price, and no call runs once the money is spent. `litellm.acompletion` is scripted."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from core import llm
from core.config import Settings
from core.db import get_session_factory
from core.llm import ChatMessage, LLMError, LLMGateway, _cost
from core.model_catalog import BudgetConfig, CatalogDefaults, ModelCatalog, ModelEntry, Pricing
from core.tracing import Tracer
from core.usage import UsageLedger, set_usage_user, usage_scope
from models import LlmUsage
from tests.conftest import TEST_USER

PRICED = ModelEntry(
    id="priced", label="Priced", provider="test", litellm_model="fake/model",
    pricing=Pricing(input_per_mtok=2.0, output_per_mtok=10.0),
)  # fmt: skip


class Label(BaseModel):
    label: str


def gateway(daily_usd: float | None = None, session_factory=None) -> LLMGateway:
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://x@y/z")  # type: ignore[call-arg]
    budget = BudgetConfig(daily_usd=daily_usd)
    catalog = ModelCatalog([PRICED], CatalogDefaults(chat="priced", cheap="priced"), settings)
    ledger = UsageLedger(session_factory or get_session_factory(), budget)
    return LLMGateway(catalog, Tracer(None, "http://x", "atlas"), ledger)


def scripted(monkeypatch, replies: list[str]) -> list[dict]:
    calls: list[dict] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=replies[len(calls) - 1])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            # 1,000 in + 100 out at $2/$10 per million = $0.003
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100),
        )

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    return calls


async def rows() -> list[LlmUsage]:
    async with get_session_factory()() as session:
        return list((await session.scalars(select(LlmUsage))).all())


def ask() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="hi")]


def test_config_price_beats_litellm_map():
    """LiteLLM priced Haiku 5.5 at $0; our own price must win."""
    assert _cost(PRICED, 1_000_000, 1_000_000) == pytest.approx(12.0)


async def test_every_attempt_is_recorded_for_the_user(db, monkeypatch):
    scripted(monkeypatch, ['{"nope": 1}', '{"label": "ok"}'])  # invalid, then retried
    set_usage_user(TEST_USER.id)
    await gateway().complete_structured("priced", ask(), Label, name="classify_intent")
    recorded = await rows()
    assert len(recorded) == 2  # the failed attempt cost money too
    assert {r.purpose for r in recorded} == {"classify_intent"}
    assert {r.user_id for r in recorded} == {TEST_USER.id}
    assert sum(r.cost_usd for r in recorded) == Decimal("0.006")


async def test_daily_budget_blocks_the_call_before_it_is_made(db, monkeypatch):
    calls = scripted(monkeypatch, ['{"label": "ok"}'])
    async with get_session_factory()() as session:
        session.add(LlmUsage(
            model_id="priced", purpose="chat", source="app",
            input_tokens=1, output_tokens=1, cost_usd=Decimal("2.5"),
        ))  # fmt: skip
        await session.commit()
    with pytest.raises(LLMError) as exc:
        await gateway(daily_usd=2.0).complete_structured("priced", ask(), Label)
    assert exc.value.kind == "budget"
    assert calls == []  # refused before spending anything


async def test_run_budget_stops_an_eval_but_not_the_first_call(db, monkeypatch):
    scripted(monkeypatch, ['{"label": "a"}', '{"label": "b"}'])
    gw = gateway()
    with usage_scope("eval", budget_usd=0.002) as scope:
        await gw.complete_structured("priced", ask(), Label)  # $0.003: allowed, then over
        with pytest.raises(LLMError) as exc:
            await gw.complete_structured("priced", ask(), Label)
    assert exc.value.kind == "budget" and scope.spent_usd == pytest.approx(0.003)
    assert [r.source for r in await rows()] == ["eval"]


async def test_a_broken_ledger_never_blocks_an_answer(monkeypatch):
    scripted(monkeypatch, ['{"label": "ok"}'])

    def broken_factory():
        raise RuntimeError("database down")

    gw = gateway(daily_usd=1.0, session_factory=broken_factory)
    parsed, _ = await gw.complete_structured("priced", ask(), Label)
    assert parsed.label == "ok"


async def test_analytics_reports_spend_by_purpose_and_user(client, monkeypatch):
    async with get_session_factory()() as session:
        session.add_all([
            LlmUsage(model_id="priced", purpose="chat", source="app", user_id=TEST_USER.id,
                     input_tokens=10, output_tokens=5, cost_usd=Decimal("0.02")),
            LlmUsage(model_id="priced", purpose="classify_intent", source="app",
                     user_id=TEST_USER.id, input_tokens=10, output_tokens=1,
                     cost_usd=Decimal("0.001")),
            LlmUsage(model_id="free", purpose="eval_judge", source="eval",
                     input_tokens=10, output_tokens=1, cost_usd=None),
        ])  # fmt: skip
        await session.commit()

    costs = (await client.get("/api/analytics")).json()["costs"]
    assert costs["spent_today_usd"] == pytest.approx(0.021)
    assert costs["unpriced_calls"] == 1
    assert [p["purpose"] for p in costs["by_purpose"]][:2] == ["chat", "classify_intent"]
    assert {u["name"] for u in costs["by_user"]} == {TEST_USER.name, "eval"}
    assert {d["model_id"] for d in costs["by_day"]} == {"priced", "free"}
