"""Simulated Acme Jira as an MCP server (Phase 5).

    docker compose up -d mcp-jira      (python -m mcp_servers.jira, port 8101, path /mcp)

The same tables the Outbox shows (models/simulated.py). Swapping in a real Jira would mean
pointing Atlas at a real Jira MCP server instead: no Atlas code changes, just config/mcp.yaml.
Tool annotations (read-only, destructive) are hints for clients; Atlas does NOT trust them
for approval decisions (see integrations/mcp_tools.py).
"""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from core.db import get_session_factory
from mcp_servers.common import serve_http
from simulated.store import SimulatedJira

PORT = 8101

server = MCPServer(
    name="acme-jira",
    title="Acme Jira (simulated)",
    instructions="Acme Corp's ticket system. Projects: IT, HR, FIN, SEC.",
)


def _jira() -> SimulatedJira:
    return SimulatedJira(get_session_factory())


def _ticket(t: Any) -> dict[str, Any]:
    return {
        "key": t.key, "project": t.project, "summary": t.summary, "description": t.description,
        "priority": t.priority, "status": t.status, "created_at": t.created_at.isoformat(),
    }  # fmt: skip


@server.tool(
    title="Create ticket",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
)
async def create_ticket(
    project: Annotated[
        Literal["IT", "HR", "FIN", "SEC"],
        Field(
            description="IT = laptops, accounts, software; HR = leave, benefits, people; "
            "FIN = expenses, travel; SEC = security incidents, phishing, lost devices."
        ),
    ],
    summary: Annotated[str, Field(min_length=5, max_length=120, description="One-line title.")],
    description: Annotated[
        str, Field(min_length=5, max_length=2000, description="What happened and what is needed.")
    ],
    priority: Annotated[
        Literal["low", "medium", "high"],
        Field(description="high only if work is blocked or security is at risk."),
    ] = "medium",
) -> dict[str, Any]:
    """Open a ticket in Acme's Jira for the right team."""
    ticket = await _jira().create_ticket(project, summary, description, priority)
    return {"key": ticket.key, "status": ticket.status, "summary": ticket.summary}


@server.tool(title="List tickets", annotations=ToolAnnotations(read_only_hint=True))
async def list_tickets(
    project: Annotated[str | None, Field(description="IT, HR, FIN or SEC; empty = all.")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """The most recent tickets, newest first."""
    tickets = [t for t in await _jira().list_tickets() if project in (None, "", t.project)]
    return {"tickets": [_ticket(t) for t in tickets[:limit]]}


if __name__ == "__main__":
    serve_http(server, PORT)
