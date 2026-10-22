# Decision log

Important choices, newest at the bottom. Format: date · decision · why · alternatives considered.

## 2026-10-19 · Phase 1 plan decisions

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Langfuse **v3** self-hosted (web + worker + ClickHouse + MinIO), reusing our Postgres (separate `langfuse` DB) and Redis | v3 is the supported version; v2 is legacy. ClickHouse is Langfuse's internal analytics store, not app data, so "one database for app data" still holds | Langfuse v2 (single container, but legacy); Langfuse Cloud (no infra, but data leaves the machine) |
| SSE written by hand with FastAPI `StreamingResponse` | ~10 lines; makes the wire format visible for learning | `sse-starlette` library |
| Custom `useChatStream` hook instead of Vercel AI SDK `useChat` | `useChat` expects the AI SDK stream protocol; our `StreamEvent` contract must be the single source of truth (principle 4) | `useChat` with the backend emitting AI SDK protocol; AI SDK custom transport |
| Client generates conversation UUIDs | No extra "conversation created" event needed; event contract stays at 7 types | Server creates id and returns it in `done` or a header |
| Selectable models in `config/models.yaml`, served by `GET /api/models` | Config-driven (principle 8); UI never hard-codes model names | Hard-coded list in frontend; env vars |
| Ollama runs on the host, reached via `host.docker.internal` | Docker on macOS cannot use the Mac GPU (Metal), so containerised Ollama is very slow | Ollama container |
| `docker-compose.yml` in repo root; `infra/` holds init scripts + deploy configs | `docker compose up` works with no `-f` flag | `infra/docker-compose.yml` + `-f` flag or root `include:` |
| Tests use a real `atlas_test` Postgres DB + a fake LLM | pgvector only exists in Postgres; a fake LLM makes tests free and deterministic | SQLite (wrong engine); mocking the DB layer |

## 2026-10-19 · `backend/mcp_integration/` instead of `backend/mcp/`

- **Why:** with `backend/` on the Python path, a local `mcp/` package shadows the official `mcp` SDK, so
  `import mcp` would load our folder and break the SDK in Phase 5.
- **Alternatives:** wrap all backend code in an `atlas/` package (bigger change to the layout in the plan);
  keep `mcp/` and rely on import tricks (fragile).
