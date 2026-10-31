"""The agent's tools (Phase 4). Each one implements core.interfaces.tool.Tool.

    read-only (run right away)              write (pause for human approval first)
    search_docs      knowledge base search  create_ticket       simulated Jira
    query_org_chart  knowledge graph        post_slack_message  simulated Slack
    calculator       exact arithmetic

Retrieval tools return {"chunks": [...]}: the agent numbers those passages across all its
searches, so the final answer can cite them as [n] exactly like the RAG chat.

Phase 5: Jira and Slack tools come from MCP servers (integrations/mcp_tools.py), discovered
at startup. If a server is down, the direct tools above stand in for its tools, so the
agent keeps working; the Settings page shows which one is in use.
"""

from functools import lru_cache

from core.db import get_session_factory
from core.interfaces.tool import Tool
from core.rag_config import get_rag_config
from integrations.mcp_tools import get_mcp_registry
from retrieval import build_retriever, get_retriever
from simulated.store import SimulatedJira, SimulatedSlack
from tools.calculator import Calculator
from tools.org_chart import QueryOrgChart
from tools.search_docs import SearchDocs
from tools.slack import PostSlackMessage
from tools.tickets import CreateTicket


@lru_cache
def get_tools() -> tuple[Tool, ...]:
    session_factory = get_session_factory()
    local: list[Tool] = [
        SearchDocs(get_retriever(), get_rag_config().retrieval.top_k),
        QueryOrgChart(build_retriever("graph")),
        Calculator(),
    ]
    direct_writes: list[Tool] = [
        CreateTicket(SimulatedJira(session_factory)),
        PostSlackMessage(SimulatedSlack(session_factory)),
    ]
    remote = get_mcp_registry().tools
    remote_names = {t.name for t in remote}
    fallbacks = [t for t in direct_writes if t.name not in remote_names]
    return (*local, *remote, *fallbacks)


__all__ = ["get_tools"]
