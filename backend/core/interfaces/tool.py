"""`Tool`: an action an agent can take. Implemented in Phase 4 (and Phase 5 via MCP).

How tool calling works: we send the model each tool's name, description and a JSON schema of
its inputs. The model doesn't run anything; it replies with "call `create_ticket` with
{...}". We validate those arguments against the schema, run the tool ourselves, and send the
result back so the model can continue. So a tool is three things:

    name + description  -> how the model decides WHEN to use it (write these carefully!)
    input_model         -> a Pydantic model; its JSON schema tells the model WHAT to send,
                           and validating against it rejects malformed arguments
    run()               -> the actual Python that does the work

Tools (backend/tools/): search_docs, query_org_chart, calculator (read-only);
create_ticket, post_slack_message (write: always need approval).
MCP-backed tools (Phase 5) are adapters that implement this same class.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel


class ToolResult(BaseModel):
    """What a tool returns. Errors are values, not exceptions: the model sees the error
    message and can recover (fix its arguments, try another tool) instead of crashing."""

    ok: bool
    output: Any = None
    error: str | None = None


class Tool[InputT: BaseModel](ABC):
    """Base class for tools. `InputT` is the Pydantic model describing the tool's arguments.

    Example (Phase 4):
        class CalculatorInput(BaseModel):
            expression: str = Field(description="Arithmetic only, e.g. '16 * 5'")

        class Calculator(Tool[CalculatorInput]):
            name = "calculator"
            description = "Evaluate an arithmetic expression exactly."
            input_model = CalculatorInput

            async def run(self, args: CalculatorInput) -> ToolResult: ...
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    # True for anything that writes to an external system (Jira, Slack, email).
    # The agent must emit an `approval_request` event and wait for a human "yes" first.
    requires_approval: ClassVar[bool] = False

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        """The input schema sent to the model in the tool definition."""
        return cls.input_model.model_json_schema()

    @classmethod
    def definition(cls) -> dict[str, Any]:
        """The tool as the model sees it (OpenAI function format; LiteLLM converts it)."""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.json_schema(),
            },
        }

    def describe_call(self, args: InputT) -> str:
        """One line for a human, e.g. on the approval card: what exactly will happen."""
        return f"{self.name}({args.model_dump_json()})"

    @abstractmethod
    async def run(self, args: InputT) -> ToolResult:
        """Do the work. `args` is already validated against `input_model`."""
