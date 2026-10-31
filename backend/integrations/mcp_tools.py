"""Atlas as an MCP *client*: discover tools on MCP servers and offer them to the agents.

    startup:  for each server in config/mcp.yaml -> list_tools() -> one McpTool per tool
    agent:    McpTool behaves like any other Tool (same approval rules, same events)
    call:     McpTool.run() -> call_tool() on the server -> ToolResult

The trust boundary. An MCP server describes its own tools, including hints like "read-only".
A server could be wrong, or malicious, so Atlas never lets a server decide what runs without
approval: every MCP tool requires approval unless config/mcp.yaml lists it as read-only.
Tool descriptions also reach the model's prompt, so only connect servers you trust.
"""

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any

import jsonschema
import yaml
from mcp.client.client import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent
from mcp.types import Tool as McpToolSpec
from pydantic import BaseModel, ConfigDict, Field

from core.config import REPO_ROOT
from core.interfaces.tool import Tool, ToolArgumentError, ToolResult

logger = logging.getLogger(__name__)

DISCOVERY_ATTEMPTS = 5  # the servers may still be starting when the backend does
CALL_TIMEOUT_SECONDS = 20


class McpServerConfig(BaseModel):
    name: str
    url: str
    read_only_tools: list[str] = Field(default_factory=list)
    summaries: dict[str, str] = Field(default_factory=dict)


class McpConfig(BaseModel):
    enabled: bool = True
    servers: list[McpServerConfig] = Field(default_factory=list)


@lru_cache
def get_mcp_config() -> McpConfig:
    path = REPO_ROOT / "config" / "mcp.yaml"
    if not path.exists():
        return McpConfig()
    return McpConfig.model_validate(yaml.safe_load(path.read_text()))


class McpArgs(BaseModel):
    """Arguments of an MCP tool: validated against the server's JSON Schema, kept as-is."""

    model_config = ConfigDict(extra="allow")


class McpTool(Tool[McpArgs]):
    input_model = McpArgs

    def __init__(
        self,
        server: str,
        target: str | MCPServer,
        spec: McpToolSpec,
        *,
        read_only: bool,
        summary: str | None = None,
    ):
        self.server = server
        self._target = target  # a URL, or an in-process server (tests)
        self._schema = spec.input_schema
        self._summary = summary
        self.name = spec.name  # type: ignore[misc]  # per instance: tools come from the server
        self.description = spec.description or spec.title or spec.name  # type: ignore[misc]
        self.requires_approval = not read_only  # type: ignore[misc]

    def json_schema(self) -> dict[str, Any]:
        return self._schema

    def parse_arguments(self, arguments: dict[str, Any]) -> McpArgs:
        try:
            jsonschema.validate(arguments, self._schema)
        except jsonschema.ValidationError as exc:
            where = ".".join(str(p) for p in exc.absolute_path)
            raise ToolArgumentError(f"{where}: {exc.message}" if where else exc.message) from exc
        return McpArgs(**arguments)

    def describe_call(self, args: McpArgs) -> str:
        # Arguments the model left out take the schema's defaults, as on the server.
        properties = self._schema.get("properties", {})
        defaults = {k: v["default"] for k, v in properties.items() if "default" in v}
        values = {**defaults, **args.model_dump()}
        if self._summary:
            try:
                return self._summary.format(**values)
            except (KeyError, IndexError, ValueError):
                pass
        return f"{self.server}: {self.name} {json.dumps(values)[:120]}"

    async def run(self, args: McpArgs) -> ToolResult:
        try:
            async with Client(self._target, read_timeout_seconds=CALL_TIMEOUT_SECONDS) as client:
                result = await client.call_tool(self.name, args.model_dump())
        except Exception as exc:  # network, timeout, protocol: the model sees a clean error
            logger.warning("MCP call %s/%s failed", self.server, self.name, exc_info=True)
            return ToolResult(ok=False, error=f"The {self.server} service is unreachable: {exc}")
        text = " ".join(c.text for c in result.content if isinstance(c, TextContent))
        if result.is_error:
            return ToolResult(ok=False, error=text or "The tool reported an error.")
        return ToolResult(ok=True, output=result.structured_content or {"result": text})


async def discover(server: McpServerConfig, target: str | MCPServer | None = None) -> list[McpTool]:
    """One server's tools as McpTools. Raises if the server can't be reached."""
    async with Client(target or server.url, read_timeout_seconds=CALL_TIMEOUT_SECONDS) as client:
        specs = (await client.list_tools()).tools
    return [
        McpTool(
            server.name,
            target or server.url,
            spec,
            read_only=spec.name in server.read_only_tools,
            summary=server.summaries.get(spec.name),
        )
        for spec in specs
    ]


class McpRegistry:
    """The discovered tools and each server's status, filled once at startup (main.py)."""

    def __init__(self) -> None:
        self.tools: list[McpTool] = []
        self.status: dict[str, str] = {}  # server name -> "connected" | error text

    async def connect(self, config: McpConfig) -> None:
        if not config.enabled:
            return
        for server in config.servers:
            for attempt in range(1, DISCOVERY_ATTEMPTS + 1):
                try:
                    tools = await discover(server)
                except Exception as exc:  # noqa: BLE001 - any failure = not reachable yet
                    self.status[server.name] = f"unreachable: {type(exc).__name__}"
                    if attempt < DISCOVERY_ATTEMPTS:
                        await asyncio.sleep(attempt)
                    continue
                self.tools += tools
                self.status[server.name] = "connected"
                logger.info("MCP %s: %d tools", server.name, len(tools))
                break
            else:
                logger.warning("MCP server %s unreachable; its tools are unavailable", server.name)


_registry = McpRegistry()


def get_mcp_registry() -> McpRegistry:
    return _registry
