"""calculator: exact arithmetic. Language models are unreliable at multiplying numbers; a
tool that computes is the standard fix (and a minimal example of tool calling).

Safety: the expression is parsed into a syntax tree and only numbers and + - * / // % ** and
parentheses are evaluated. Never `eval()` model output: it would run any Python it writes.
"""

import ast
import operator

from pydantic import BaseModel, Field

from core.interfaces.tool import Tool, ToolResult

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
MAX_EXPONENT = 100  # 10 ** 10 ** 10 would hang the server


class CalculatorInput(BaseModel):
    expression: str = Field(max_length=200, description="Arithmetic only, e.g. '16 * 5 + 3'.")


class Calculator(Tool[CalculatorInput]):
    name = "calculator"
    description = "Evaluate an arithmetic expression exactly. Use it for any calculation."
    input_model = CalculatorInput

    def describe_call(self, args: CalculatorInput) -> str:
        return f"Calculate {args.expression}"

    async def run(self, args: CalculatorInput) -> ToolResult:
        try:
            value = evaluate(ast.parse(args.expression, mode="eval").body)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
            return ToolResult(ok=False, error=f"Can't evaluate: {exc}")
        return ToolResult(ok=True, output={"result": round(value, 10)})


def evaluate(node: ast.expr) -> float:
    match node:
        case ast.Constant(value=int() | float() as number) if not isinstance(number, bool):
            return number
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _OPERATORS:
            a, b = evaluate(left), evaluate(right)
            if isinstance(op, ast.Pow) and abs(b) > MAX_EXPONENT:
                raise ValueError("exponent too large")
            return _OPERATORS[type(op)](a, b)
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _OPERATORS:
            return _OPERATORS[type(op)](evaluate(operand))
    raise ValueError("only numbers and + - * / // % ** ( ) are allowed")
