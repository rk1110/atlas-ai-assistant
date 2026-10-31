"""The Outbox API (Phase 4): what the agent's approved actions "sent" to the simulated
Jira and Slack. Read-only; the only way to create these is an approved agent action.

    GET /api/outbox   tickets and Slack messages, newest first
"""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import JiraDep, SlackDep

router = APIRouter(prefix="/api/outbox", tags=["outbox"])


class TicketOut(BaseModel):
    key: str
    project: str
    summary: str
    description: str
    priority: str
    status: str
    created_at: datetime


class SlackMessageOut(BaseModel):
    channel: str
    text: str
    created_at: datetime


class Outbox(BaseModel):
    tickets: list[TicketOut]
    messages: list[SlackMessageOut]


@router.get("")
async def outbox(jira: JiraDep, slack: SlackDep) -> Outbox:
    tickets = await jira.list_tickets()
    messages = await slack.list_messages()
    return Outbox(
        tickets=[TicketOut.model_validate(t, from_attributes=True) for t in tickets],
        messages=[SlackMessageOut.model_validate(m, from_attributes=True) for m in messages],
    )
