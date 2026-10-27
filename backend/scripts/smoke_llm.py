"""Smoke test for the LLM gateway: stream one short reply from each model (or the ones named).

Run inside the backend container, where all env vars are set:
    docker compose exec backend python -m scripts.smoke_llm
    docker compose exec backend python -m scripts.smoke_llm claude-haiku gpt-oss-cloud

This makes real API calls (a fraction of a cent each). It is NOT part of the pytest suite.
"""

import asyncio
import sys

from api.deps import get_catalog, get_gateway
from core.llm import ChatMessage, Completion, LLMError, TextDelta
from core.tracing import get_tracer

PROMPT = [
    ChatMessage(role="system", content="You are a concise assistant."),
    ChatMessage(role="user", content="In one sentence: who was Atlas in Greek mythology?"),
]


async def smoke(model_id: str) -> None:
    print(f"\n=== {model_id} ===")
    try:
        async for chunk in get_gateway().stream_chat(model_id, PROMPT):
            if isinstance(chunk, TextDelta):
                print(chunk.text, end="", flush=True)  # tokens appear as they stream
            elif isinstance(chunk, Completion):
                cost = f"${chunk.cost_usd:.6f}" if chunk.cost_usd is not None else "n/a"
                print(
                    f"\n--> {chunk.input_tokens} in / {chunk.output_tokens} out tokens | "
                    f"cost {cost} | first token {chunk.time_to_first_token_ms} ms | "
                    f"total {chunk.latency_ms} ms | finish={chunk.finish_reason}"
                )
                print(f"    trace: {get_tracer().trace_url(chunk.trace_id)}")
    except LLMError as err:
        print(f"[{err.kind}] {err.message}\n    detail (logs only): {err.detail}")


async def main(model_ids: list[str]) -> None:
    for model_id in model_ids or [entry.id for entry in get_catalog().list()]:
        await smoke(model_id)
    get_tracer().flush()  # scripts exit fast: send buffered traces before the process ends


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
