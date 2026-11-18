"""Who is spending, and how much (Phase 7B): the usage ledger and the budget cap.

The gateway records every model call here (one `llm_usage` row) and asks before every call
whether the money is still there. Two caps:

- **Daily budget** (`budget.daily_usd` in config/models.yaml): today's spend across all
  users, chats, evals and ingestion. Protects the account from a runaway loop or script.
- **Scope budget** (`usage_scope(budget_usd=...)`): one eval run's own cap, e.g.
  `python -m evals.run --budget 0.50`. Stops the run, not the app.

Both are checked BEFORE a call, because a call's cost is only known after it. So a cap can be
overshot by one call's cost; with Atlas's call sizes that is a fraction of a cent.

Like the reader's access tags (core/access.py), the current user and source live in a
context variable: set once per request or script, read by the gateway deep inside any call,
without passing `user_id` through every function in between.
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.model_catalog import BudgetConfig
from models.usage import LlmUsage

logger = logging.getLogger(__name__)


@dataclass
class UsageScope:
    source: str = "app"
    user_id: uuid.UUID | None = None
    budget_usd: float | None = None  # this scope's own cap (an eval run); None = none
    spent_usd: float = 0.0  # what this scope has spent so far


_scope: ContextVar[UsageScope | None] = ContextVar("usage_scope", default=None)


def current_scope() -> UsageScope:
    return _scope.get() or UsageScope()


def set_usage_user(user_id: uuid.UUID | None) -> None:
    """Per request (api/deps.py, next to the access tags): calls are charged to this user."""
    _scope.set(UsageScope(source="app", user_id=user_id))


@contextmanager
def usage_scope(source: str, budget_usd: float | None = None) -> Iterator[UsageScope]:
    """For scripts: label their calls ("eval", "ingestion") and optionally cap their spend."""
    scope = UsageScope(source=source, budget_usd=budget_usd)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


def begin_script(source: str, budget_usd: float | None = None) -> UsageScope:
    """For a script's main(): label every call it makes, for the rest of the process.
    Set before `asyncio.run()`, which copies the current context into its task."""
    scope = UsageScope(source=source, budget_usd=budget_usd)
    _scope.set(scope)
    return scope


def utc_midnight() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class UsageLedger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], budget: BudgetConfig):
        self._session_factory = session_factory
        self._budget = budget

    async def over_budget(self) -> str | None:
        """Why the next call must not run, or None. A ledger failure (DB down) never blocks
        a call: the cap is a safety net, and the call would fail on its own anyway."""
        scope = current_scope()
        if scope.budget_usd is not None and scope.spent_usd >= scope.budget_usd:
            return f"This run's budget of ${scope.budget_usd:.2f} is used up."
        if self._budget.daily_usd is None:
            return None
        try:
            spent = await self.spent_today()
        except Exception:
            logger.warning("budget check failed; allowing the call", exc_info=True)
            return None
        if spent >= self._budget.daily_usd:
            return f"Today's model budget of ${self._budget.daily_usd:.2f} is used up."
        return None

    async def spent_today(self) -> float:
        async with self._session_factory() as session:
            total = await session.scalar(
                select(func.coalesce(func.sum(LlmUsage.cost_usd), 0)).where(
                    LlmUsage.created_at >= utc_midnight()
                )
            )
        return float(total or 0)

    async def record(
        self,
        model_id: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """Never raises: losing one ledger row must not fail the user's answer."""
        scope = current_scope()
        scope.spent_usd += cost_usd or 0.0
        try:
            async with self._session_factory() as session:
                session.add(
                    LlmUsage(
                        model_id=model_id,
                        purpose=purpose,
                        source=scope.source,
                        user_id=scope.user_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
                    )
                )
                await session.commit()
        except Exception:
            logger.warning("could not record usage for %s (%s)", model_id, purpose, exc_info=True)
