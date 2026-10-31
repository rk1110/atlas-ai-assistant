"""MCP (Phase 5): our servers, the client adapter (McpTool), and the trust rules.
Everything runs in-process: the MCP Client accepts a server object instead of a URL."""

from typing import Any

import pytest
from httpx import AsyncClient
from mcp.client.client import Client

import mcp_servers.atlas as atlas_server
from core.interfaces.tool import ToolArgumentError
from integrations.mcp_tools import McpRegistry, McpServerConfig, discover, get_mcp_registry
from mcp_servers.jira import server as jira_server
from mcp_servers.slack import server as slack_server
from tests.conftest import FakeRetriever, make_chunk

JIRA = McpServerConfig(
    name="jira",
    url="http://unused",
    read_only_tools=["list_tickets"],
    summaries={"create_ticket": "Create a {priority}-priority {project} ticket: “{summary}”"},
)


async def test_jira_tools_are_discovered_with_default_deny_approval(db: None):
    tools = {t.name: t for t in await discover(JIRA, target=jira_server)}

    assert tools["create_ticket"].requires_approval is True  # not listed as read-only
    assert tools["list_tickets"].requires_approval is False
    definition = tools["create_ticket"].definition()["function"]
    assert definition["parameters"]["properties"]["project"]["enum"] == ["IT", "HR", "FIN", "SEC"]


async def test_mcp_tool_validates_describes_and_calls_the_server(db: None):
    tools = {t.name: t for t in await discover(JIRA, target=jira_server)}
    create = tools["create_ticket"]

    with pytest.raises(ToolArgumentError, match="project"):
        create.parse_arguments({"project": "XX", "summary": "Broken", "description": "Broken!"})
    args = create.parse_arguments(
        {"project": "IT", "summary": "Broken screen", "description": "Screen cracked."}
    )
    assert create.describe_call(args) == "Create a medium-priority IT ticket: “Broken screen”"

    result = await create.run(args)
    assert result.ok and result.output["key"] == "IT-1001"
    listed = await tools["list_tickets"].run(tools["list_tickets"].parse_arguments({}))
    assert [t["key"] for t in listed.output["tickets"]] == ["IT-1001"]


async def test_server_side_errors_and_unreachable_servers_become_tool_errors(db: None):
    [post, _] = sorted(
        await discover(McpServerConfig(name="slack", url="x"), target=slack_server),
        key=lambda t: t.name != "post_slack_message",
    )
    bad = post.parse_arguments({"channel": "#ok", "text": "hi"})
    bad.channel = "not a channel"  # bypass client validation: the server must still refuse
    result = await post.run(bad)
    assert result.ok is False

    offline = McpRegistry()
    offline_config = McpServerConfig(name="jira", url="http://127.0.0.1:9/mcp")
    from integrations import mcp_tools

    mcp_tools.DISCOVERY_ATTEMPTS, saved = 1, mcp_tools.DISCOVERY_ATTEMPTS
    try:
        await offline.connect(mcp_tools.McpConfig(servers=[offline_config]))
    finally:
        mcp_tools.DISCOVERY_ATTEMPTS = saved
    assert offline.tools == [] and offline.status["jira"].startswith("unreachable")


async def test_atlas_server_exposes_read_only_tools(monkeypatch: pytest.MonkeyPatch):
    retriever = FakeRetriever([make_chunk(1, "Laptops are replaced every 3 years.")])
    monkeypatch.setattr(atlas_server, "get_retriever", lambda: retriever)
    async with Client(atlas_server.server) as client:
        tools = (await client.list_tools()).tools
        result = await client.call_tool("search_knowledge_base", {"query": "laptop", "top_k": 1})

    assert {t.name for t in tools} == {"search_knowledge_base", "query_org_chart", "ask_atlas"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
    passages: list[dict[str, Any]] = result.structured_content["passages"]  # type: ignore[index]
    assert passages[0]["text"] == "Laptops are replaced every 3 years."


async def test_integrations_api_reports_servers_and_tools(client: AsyncClient, db: None):
    registry = get_mcp_registry()
    registry.tools = await discover(JIRA, target=jira_server)
    registry.status = {"jira": "connected"}
    try:
        servers = {s["name"]: s for s in (await client.get("/api/integrations")).json()}
    finally:
        registry.tools, registry.status = [], {}
    assert servers["jira"]["status"] == "connected"
    approvals = {t["name"]: t["requires_approval"] for t in servers["jira"]["tools"]}
    assert approvals == {"create_ticket": True, "list_tickets": False}
