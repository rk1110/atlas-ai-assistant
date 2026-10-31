"""Simulated Acme Slack as an MCP server (Phase 5).

docker compose up -d mcp-slack     (python -m mcp_servers.slack, port 8102, path /mcp)
"""

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from core.db import get_session_factory
from mcp_servers.common import serve_http
from simulated.store import SimulatedSlack

PORT = 8102

# The channels named in the Acme documents (teams-and-people.md, about-acme.md).
CHANNELS = {
    "#ask-it": "IT Team: laptops, accounts, software",
    "#ask-people": "People Team: leave, working hours, benefits",
    "#ask-finance": "Finance Team: expenses, travel",
    "#security-incidents": "Security Team: phishing, lost devices, incidents",
    "#eng-help": "Engineering", "#product": "Product", "#design": "Design",
    "#sales": "Sales", "#support": "Customer Support", "#announcements": "Company announcements",
}  # fmt: skip

server = MCPServer(
    name="acme-slack",
    title="Acme Slack (simulated)",
    instructions="Acme Corp's Slack. Use list_channels to find the right team channel.",
)


def _slack() -> SimulatedSlack:
    return SimulatedSlack(get_session_factory())


@server.tool(
    title="Post message",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
)
async def post_slack_message(
    channel: Annotated[
        str,
        Field(
            pattern=r"^#[a-z0-9][a-z0-9_-]{0,78}$",
            description="Channel name starting with #, e.g. '#ask-it'.",
        ),
    ],
    text: Annotated[str, Field(min_length=2, max_length=1000, description="Plain text.")],
) -> dict[str, Any]:
    """Post a message to an Acme Slack channel."""
    message = await _slack().post_message(channel, text)
    return {"channel": message.channel, "posted": True}


@server.tool(title="List channels", annotations=ToolAnnotations(read_only_hint=True))
async def list_channels() -> dict[str, Any]:
    """Acme's team channels and what each is for."""
    return {"channels": [{"name": n, "purpose": p} for n, p in CHANNELS.items()]}


if __name__ == "__main__":
    serve_http(server, PORT)
