# MCP in Atlas

Atlas speaks the Model Context Protocol in both directions.

| Direction | What | Transport | Where |
| --- | --- | --- | --- |
| Atlas **uses** MCP servers | Simulated Acme Jira and Slack | Streamable HTTP | `mcp-jira` (port 8101), `mcp-slack` (port 8102); `config/mcp.yaml` |
| Atlas **is** an MCP server | `search_knowledge_base`, `query_org_chart`, `ask_atlas` (read-only) | stdio | `python -m mcp_servers.atlas` |

## Use Atlas from Claude Desktop

1. Start Atlas: `docker compose up -d`.
2. In Claude Desktop, open **Settings → Developer → Edit Config**, and add this inside `"mcpServers"`. Use the absolute path to *your* `docker-compose.yml`, and the full path to `docker` if Claude Desktop can't find it (`which docker`):

```json
{
  "mcpServers": {
    "atlas": {
      "command": "docker",
      "args": [
        "compose", "-f", "/Users/rutvik.kathrecha/Desktop/atlas/docker-compose.yml",
        "exec", "-T", "backend", "python", "-m", "mcp_servers.atlas"
      ]
    }
  }
}
```

3. Restart Claude Desktop. The tools menu should list **atlas** with 3 tools.
4. Try: "Use Atlas to find out how often Acme replaces laptops, with the source."

`-T` matters: it gives the server a plain pipe, not a terminal, so stdout stays clean protocol messages.

## Inspect the servers yourself

The MCP Inspector is a web UI for poking at any MCP server (it runs from npm, outside Atlas):

```bash
npx @modelcontextprotocol/inspector
```

- **Jira:** transport "Streamable HTTP", URL `http://localhost:8101/mcp`.
- **Slack:** `http://localhost:8102/mcp`.
- **Atlas:** transport "STDIO", command `docker`, arguments as in the JSON above.

## Safety rules

- Every tool from an MCP server needs approval in Atlas unless `config/mcp.yaml` lists it under `read_only_tools`. Servers can label their own tools read-only, but Atlas doesn't take a server's word for it.
- Atlas's own server is read-only: an outside client can search and ask, but never trigger a Jira ticket or a Slack post.
- Tool descriptions from a server go into the model's prompt. Only connect servers you trust.
