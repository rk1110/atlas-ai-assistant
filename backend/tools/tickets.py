"""create_ticket: open a ticket in (simulated) Jira. A write tool: always needs approval."""

from typing import Literal

from pydantic import BaseModel, Field

from core.interfaces.tool import Tool, ToolResult
from simulated.store import SimulatedJira


class CreateTicketInput(BaseModel):
    project: Literal["IT", "HR", "FIN", "SEC"] = Field(
        description="IT = laptops, accounts, software; HR = leave, benefits, people; "
        "FIN = expenses, travel; SEC = security incidents, phishing, lost devices."
    )
    summary: str = Field(min_length=5, max_length=120, description="One-line title.")
    description: str = Field(
        min_length=5, max_length=2000, description="What happened and what is needed."
    )
    priority: Literal["low", "medium", "high"] = Field(
        default="medium", description="high only if work is blocked or security is at risk."
    )


class CreateTicket(Tool[CreateTicketInput]):
    name = "create_ticket"
    description = (
        "Open a ticket in Acme's Jira for the right team. The user is shown the exact ticket "
        "and must approve it before it is created, so call this directly when they ask for "
        "a ticket; don't ask for permission in text first."
    )
    input_model = CreateTicketInput
    requires_approval = True

    def __init__(self, jira: SimulatedJira):
        self._jira = jira

    def describe_call(self, args: CreateTicketInput) -> str:
        return f"Create a {args.priority}-priority {args.project} ticket: “{args.summary}”"

    async def run(self, args: CreateTicketInput) -> ToolResult:
        ticket = await self._jira.create_ticket(
            args.project, args.summary, args.description, args.priority
        )
        return ToolResult(
            ok=True, output={"key": ticket.key, "status": ticket.status, "summary": ticket.summary}
        )
