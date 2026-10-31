"""search_docs: the agent's way into the knowledge base (the same retriever the chat uses)."""

from pydantic import BaseModel, Field

from core.interfaces.retriever import Retriever
from core.interfaces.tool import Tool, ToolResult


class SearchDocsInput(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=300,
        description="A standalone search query, e.g. 'laptop replacement policy Acme'.",
    )


class SearchDocs(Tool[SearchDocsInput]):
    name = "search_docs"
    description = (
        "Search the company knowledge base (Acme Corp policies and the GitLab handbook). "
        "Use it before answering any question about company policies, processes or facts. "
        "Returns numbered passages; cite them as [n]."
    )
    input_model = SearchDocsInput

    def __init__(self, retriever: Retriever, top_k: int):
        self._retriever = retriever
        self._top_k = top_k

    def describe_call(self, args: SearchDocsInput) -> str:
        return f"Search the knowledge base for “{args.query}”"

    async def run(self, args: SearchDocsInput) -> ToolResult:
        chunks = await self._retriever.retrieve(args.query, top_k=self._top_k)
        return ToolResult(ok=True, output={"chunks": [c.model_dump() for c in chunks]})
