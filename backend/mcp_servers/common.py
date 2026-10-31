"""Run an MCP server over Streamable HTTP inside Docker Compose."""

import os

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


def serve_http(server: MCPServer, port: int) -> None:
    """MCP's HTTP transport checks the Host header (DNS-rebinding protection: a malicious web
    page can't make your browser talk to a local server). Inside Docker the other services
    reach us as e.g. "mcp-jira:8101", so that name must be allowed explicitly."""
    service = os.environ.get("MCP_SERVICE_HOST", "localhost")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{service}:{port}", f"localhost:{port}", f"127.0.0.1:{port}"],
        allowed_origins=[],
    )
    app = server.streamable_http_app(
        transport_security=security, stateless_http=True, host="0.0.0.0"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
