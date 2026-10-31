"""Atlas as an MCP *server* (Phase 5): Claude Desktop, IDEs or any MCP client can use
Atlas's knowledge base as a tool.

    python -m mcp_servers.atlas          (stdio: the client starts it and talks over stdin/out)

Claude Desktop config (Settings > Developer > Edit config), see docs/mcp.md:
    "atlas": {"command": "docker", "args": ["compose", "-f", "<repo>/docker-compose.yml",
              "exec", "-T", "backend", "python", "-m", "mcp_servers.atlas"]}

Read-only on purpose: the tools search, look up and answer. Writing to Jira or Slack only
happens inside Atlas, behind its approval cards; an outside client can't trigger it.
stdout belongs to the protocol, so nothing here may print: logs go to stderr.
"""

import logging
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from api.deps import get_catalog, get_chat_service
from core.rag_config import get_rag_config
from retrieval import build_retriever, get_retriever

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="atlas",
    log_level="WARNING",
    title="Atlas knowledge assistant",
    instructions=(
        "Search Acme Corp's policies and the GitLab handbook, look up Acme's org chart, or ask "
        "Atlas for a cited answer. Read-only."
    ),
)


@server.tool(title="Search the knowledge base", annotations=READ_ONLY)
async def search_knowledge_base(
    query: Annotated[str, Field(min_length=2, max_length=300, description="What to look for.")],
    top_k: Annotated[int, Field(ge=1, le=10)] = 5,
) -> dict[str, Any]:
    """Find the passages most relevant to a query (hybrid search: meaning + keywords + graph)."""
    chunks = await get_retriever().retrieve(query, top_k=top_k)
    return {
        "passages": [
            {
                "rank": i,
                "title": c.title,
                "heading": c.metadata.get("heading"),
                "document_id": c.document_id,
                "url": c.url,
                "text": c.text,
            }
            for i, c in enumerate(chunks, start=1)
        ]
    }


@server.tool(title="Look up the org chart", annotations=READ_ONLY)
async def query_org_chart(
    question: Annotated[
        str, Field(min_length=2, max_length=300, description="People, teams, policies.")
    ],
) -> dict[str, Any]:
    """Who leads which team, who reports to whom, which team owns a policy or Slack channel."""
    chunks = await build_retriever("graph").retrieve(question, top_k=3)
    return {"facts": [{"document": c.title, "facts": c.text} for c in chunks]}


@server.tool(title="Ask Atlas", annotations=READ_ONLY)
async def ask_atlas(
    question: Annotated[str, Field(min_length=2, max_length=2000, description="A question.")],
) -> dict[str, Any]:
    """A short answer from Atlas, grounded in the knowledge base, with its sources."""
    result = await get_chat_service().answer(
        question, get_catalog().defaults.chat, trace_name="mcp_ask_atlas", tags=["mcp"]
    )
    if result.error_code:
        return {"error": f"Atlas couldn't answer ({result.error_code})."}
    return {
        "answer": result.answer,
        "sources": [{"n": c.citation_id, "title": c.title, "url": c.url} for c in result.citations],
    }


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    for noisy in ("LiteLLM", "litellm", "httpx2", "agents.checkpoints"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    get_rag_config()  # fail fast on bad config, before the client connects
    server.run("stdio")


if __name__ == "__main__":
    main()
