"""The four extension points of Atlas (principle 3: interfaces before implementations).

New data sources, retrievers, tools and agents are new classes implementing these; existing
code that uses the interface never changes. The fifth contract, `StreamEvent`, is in
`core/events.py`.
"""

from core.interfaces.agent import Agent, AgentState, EventEmitter
from core.interfaces.data_source import DataSource, Document
from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from core.interfaces.tool import Tool, ToolResult

__all__ = [
    "Agent", "AgentState", "Chunk", "DataSource", "Document", "EventEmitter",
    "RetrievalFilters", "Retriever", "Tool", "ToolResult",
]  # fmt: skip
