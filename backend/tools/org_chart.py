"""query_org_chart: who leads which team, who reports to whom, which team owns what (GraphRAG)."""

from pydantic import BaseModel, Field

from core.interfaces.retriever import Retriever
from core.interfaces.tool import Tool, ToolResult


class QueryOrgChartInput(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=300,
        description="Name the people, teams or policies involved, e.g. 'who leads the IT Team'.",
    )


class QueryOrgChart(Tool[QueryOrgChartInput]):
    name = "query_org_chart"
    description = (
        "Look up Acme Corp's org chart in the knowledge graph: who leads a team, who reports "
        "to whom, which team owns a policy or system, and which Slack channel reaches a team. "
        "Use it to find the right team or person, e.g. before opening a ticket."
    )
    input_model = QueryOrgChartInput

    def __init__(self, graph: Retriever):
        self._graph = graph

    def describe_call(self, args: QueryOrgChartInput) -> str:
        return f"Look up the org chart: “{args.question}”"

    async def run(self, args: QueryOrgChartInput) -> ToolResult:
        chunks = await self._graph.retrieve(args.question, top_k=3)
        if not chunks:
            return ToolResult(ok=True, output={"chunks": [], "note": "No matching entities."})
        return ToolResult(ok=True, output={"chunks": [c.model_dump() for c in chunks]})
