# backend/

FastAPI service: all AI logic lives here. The frontend only talks to this over HTTP + SSE.

| Folder | Purpose | Phase |
| --- | --- | --- |
| `api/` | FastAPI routes (chat, conversations, models, classify; later ingest, evals, admin) | 1+ |
| `core/` | Config, LiteLLM gateway, prompt registry, stream events, DB session, core interfaces | 1 |
| `models/` | SQLAlchemy ORM tables (conversations, messages, eval runs; later documents, chunks, memory) | 1+ |
| `services/` | Business logic that routes call (e.g. "run one chat turn"). Keeps routes thin and testable | 1+ |
| `ingestion/` | Load → parse → chunk → embed documents | 2 |
| `retrieval/` | Vector, keyword, hybrid, reranker, graph retrievers | 2–3 |
| `agents/` | LangGraph graphs and agents | 4–5 |
| `tools/` | Tools agents can call | 4 |
| `mcp_integration/` | MCP clients + the Atlas MCP server | 5 |
| `memory/` | Short- and long-term memory | 4 |
| `guardrails/` | Prompt-injection, PII, output checks | 7 |
| `evals/` | Golden set, metrics, runners | 1+ |
| `tests/` | pytest tests | 1+ |

> Why `mcp_integration/` and not `mcp/`? A local folder named `mcp` would shadow the official
> `mcp` Python SDK, so `import mcp` would load our folder instead of the library. See `docs/decisions.md`.
