"""Integrations API (Phase 5): which MCP servers Atlas is connected to, and their tools.

GET /api/integrations
"""

from fastapi import APIRouter
from pydantic import BaseModel

from integrations.mcp_tools import get_mcp_config, get_mcp_registry

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class IntegrationTool(BaseModel):
    name: str
    description: str
    requires_approval: bool


class IntegrationServer(BaseModel):
    name: str
    url: str
    status: str  # "connected", "unreachable: ...", or "not tried"
    tools: list[IntegrationTool]


@router.get("")
async def integrations() -> list[IntegrationServer]:
    registry = get_mcp_registry()
    return [
        IntegrationServer(
            name=server.name,
            url=server.url,
            status=registry.status.get(server.name, "not tried"),
            tools=[
                IntegrationTool(
                    name=t.name, description=t.description, requires_approval=t.requires_approval
                )
                for t in registry.tools
                if t.server == server.name
            ],
        )
        for server in get_mcp_config().servers
    ]
