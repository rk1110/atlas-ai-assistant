# Decision log

Important choices, newest at the bottom. Format: date · decision · why · alternatives considered.

## 2026-10-19 · Phase 1 plan decisions

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Langfuse self-hosted (v3 planned; **superseded: v4**, see step 2 below) (web + worker + ClickHouse + MinIO), reusing our Postgres (separate `langfuse` DB) and Redis | v3 is the supported version; v2 is legacy. ClickHouse is Langfuse's internal analytics store, not app data, so "one database for app data" still holds | Langfuse v2 (single container, but legacy); Langfuse Cloud (no infra, but data leaves the machine) |
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

## 2026-10-22 · Phase 1 step 2 (infrastructure)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| **Langfuse v4** (`4.55.0`) instead of v3 | v4 is the current release and the official compose file now uses it; same components (web, worker, ClickHouse, MinIO, Redis, Postgres) | v3 (older, would need upgrading soon) |
| Version pin rule: **newest release ≥ 14 days old** | Brand-new releases sometimes ship regressions; two weeks lets early bugs surface | Always latest (risky); a fixed old version (misses fixes) |
| Exception: **Next.js 16.4.2** (newer than 14 days) | 16.0.0–16.4.0 has an unauthenticated RCE (GHSA-2464-fhr4-w9xw); security fixes beat the age rule | Stay on 16.4.0 (vulnerable) |
| Ignored dev-only `npm audit` "high" (`braces` via eslint-config-next) | Only affects the local linter, never shipped; the suggested "fix" downgrades to Next 14 | Downgrade eslint-config-next (breaks Next 16 lint rules) |
| MinIO from `cgr.dev/chainguard/minio`, pinned by digest | MinIO stopped publishing community Docker images; Chainguard only publishes `latest`, so a digest is the only exact pin | `minio/minio` (no longer maintained); Langfuse's unpinned `latest` |
| One Redis shared by Langfuse and Atlas with `noeviction` | Langfuse's job queue must not lose keys; Atlas cache keys will use TTLs instead of eviction | Separate Redis per app (more containers; revisit in Phase 7 if the cache grows) |
| pgvector extension enabled by Alembic migration, not `init.sql` | Migrations run everywhere (incl. cloud Postgres); init scripts only run on a fresh local volume | Enable in `init.sql` |
| Backend container gets an explicit env var list, not the whole `.env` | Least privilege: the backend doesn't need Langfuse's server secrets | `env_file: .env` (simpler, leaks every secret into the container) |
| Dev containers bind-mount source + hot reload; frontend `node_modules` kept in an anonymous volume | Edit on your Mac, see changes instantly; Linux native binaries must not be overwritten by macOS ones | Rebuild image on each change (slow) |
| Python **3.13** in the image (you have 3.14 locally) | AI libraries (tokenizers, torch for sentence-transformers) reliably ship wheels for 3.13 first | 3.14 (risk of missing wheels in Phase 2–3) |

## 2026-10-27 · Phase 1 step 3a (config + LLM gateway)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Model catalog in `config/models.yaml` with **per-model `params`** (not global temperature/max_tokens) | Claude 5.5 models reject non-default `temperature` (400) while Ollama models accept it; the difference is data, not `if provider` branches | One global params block (breaks Claude); provider-specific code paths |
| Claude chat uses `reasoning_effort: low` | Claude 5.5 always thinks; effort is the only control, and low keeps chat latency down. LiteLLM maps it to `output_config.effort` | Default effort (slower, pricier for chat) |
| Server-side refusal fallback (`fallbacks: default` + beta header) on Sonnet 5.5, via `extra_body` / `extra_headers` | A wrongly-declined request is retried on a fallback model in the same call. **Not yet verified end to end**: no API credit (see below) | No fallback (a false refusal just fails) |
| `LITELLM_LOCAL_MODEL_COST_MAP=True` | Use the price map bundled with the pinned LiteLLM instead of fetching from GitHub at import: reproducible, offline-safe, no runtime download | LiteLLM default (remote fetch on every start) |
| Gateway yields provider-neutral `TextDelta` / `Completion`; errors become `LLMError(kind=...)` | Callers (chat service, evals) never depend on LiteLLM or provider exception types; the UI can react per kind | Let LiteLLM exceptions propagate |
| `billing` error kind, detected from Anthropic's "credit balance is too low" message | Anthropic sends it as a generic 400; users need "add credit or switch model", not "bad request". String match is fragile, revisit if the wording changes | Treat as `bad_request` |
| **Defaults switched to Ollama Cloud** (`gpt-oss:120b` chat, `gpt-oss:20b` cheap) | Smoke test: Anthropic account has no API credit (evaluation plan). Switch back in one line when billing is added | Block Phase 1 on billing |
| Ollama Cloud cost shows $0 | LiteLLM prices all `ollama_chat/` models at $0/token (assumes local). Ollama Cloud bills by plan usage, so per-call $0 is accurate per token but not the full cost | Custom price entries (no published per-token price) |
| Availability check: key present, or TCP probe for local servers | Lets the UI grey out models; a present key can still be rejected, which surfaces as a typed error at call time | Real test call per model (costs money, slow) |
| Explicit ruff rule set (`E,W,F,I,B,UP,BLE,ASYNC,RUF`) | Upgrading ruff must not silently change what we enforce | Ruff defaults |
| Accepted `filelock 3.32.7` CVEs (pip-audit) | LiteLLM pins `filelock<4`; 2 of 3 CVEs are Windows-only and the Linux one is in `ReadWriteLock`, which nothing in our tree uses. Re-audit on every LiteLLM bump | Force `filelock 4.x` past LiteLLM's declared range |

## 2026-10-27 · Phase 1 step 3b (prompt registry + stream events)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Prompts as one YAML file per prompt, multiple immutable versions + `active` | Reviewable in git, comparable in evals; every answer records `name@version` | Python string constants (no versioning); Langfuse prompt management (UI editing, runtime fetch; a possible later upgrade) |
| `string.Template` (`$var`) for templating | Literal `{}` (JSON examples) need no escaping; stdlib, no new dependency | `str.format` (brace escaping bugs); Jinja2 (powerful, extra dependency, logic in prompts) |
| Declared `variables` must equal the template's placeholders; render rejects missing/extra | A typo'd variable fails at startup or in tests, not as a silently broken prompt in production | `safe_substitute` (leaves `$typo` in the prompt silently) |
| All 7 `StreamEvent` types defined now as a Pydantic discriminated union on `type` | Frontend mirrors one fixed contract; later phases only emit events, never rewire | Define each event when first needed (frontend churn every phase) |
| SSE frames carry only `data: <json>` (type inside the JSON), no `event:` line | One parsing rule on the frontend: split on blank lines, parse JSON, switch on `type` | Named SSE events (`event: token`), useful with `EventSource` listeners, but we use `fetch` streams (POST body) |
| `ErrorEvent.retryable` + user-safe `message` | UI shows "Try again" only when it can help; never leaks stack traces or secrets | Raw exception text |
| `DoneEvent` carries `usage`, `prompt_ref`, optional `trace_id` | Analytics and "view trace" links get everything from the stream; `trace_id` stays optional until step 5 | Separate stats endpoint |

## 2026-10-27 · Phase 1 step 3c (core interfaces)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| `DataSource.load()` is an **async iterator** of `Document`s (plan said `-> list[Document]`) | The GitLab handbook has thousands of pages; streaming lets ingestion process each one as it arrives instead of holding all in memory | Return a list (simple, doesn't scale) |
| `Document.access_tags` (default `["public"]`) exists from day one | Phase 7 permission-aware retrieval filters on it; adding it later would mean re-ingesting everything | Add in Phase 7 |
| Retriever wrappers (hybrid, reranking) compose other `Retriever`s | Any combination can be built and A/B tested with evals without new subclasses | Inheritance hierarchy |
| `Tool` is generic over a Pydantic input model; its JSON schema is what the model sees | One definition gives the model's schema AND server-side validation of the model's arguments | Hand-written JSON schemas (drift from the code) |
| `ToolResult` returns errors as values | The model sees "error: ..." and can recover; an exception would end the agent turn | Raise exceptions |
| `Tool.requires_approval` class flag | Write tools are marked once; the agent runtime (Phase 4) enforces the approval step centrally | Each tool implementing its own approval check |
| `Agent` interface does not import LangGraph; agents return partial state updates and stream via `emit` | Agents depend on our types only; a thin adapter makes them LangGraph nodes. Partial updates match LangGraph's merge semantics | Subclass LangGraph types directly (framework lock-in) |

## 2026-10-27 · Phase 1 step 3d (database)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Async SQLAlchemy 2.0 (`Mapped[...]` typed models) + asyncpg | Requests mostly wait on I/O (LLM, DB); async lets one process serve many. Typed models catch mistakes in the editor | Sync SQLAlchemy in a thread pool; SQLModel (thinner, less control); raw SQL |
| Constraint **naming convention** on `Base.metadata` | Deterministic names (`fk_messages_conversation_id_conversations`) so later migrations can alter/drop them reliably | Postgres-generated names (differ per database, break downgrades) |
| Alembic URL from `Settings`, not `alembic.ini` | One source of truth; no second copy of the DB password in a committed file | `sqlalchemy.url` in the ini |
| Autogenerated migration, **hand-reviewed**; pgvector enabled in migration 0001 | Autogenerate doesn't handle extensions; migrations are code to review (`alembic upgrade head --sql`) | Trust autogenerate blindly; enable extension in `init.sql` (never runs on cloud DBs) |
| Readable revision ids (`--rev-id 0001`) and `<rev>_<slug>.py` filenames | Migration order is obvious when browsing the folder | Random hex ids (Alembic default) |
| Backend runs `alembic upgrade head` on start (dev compose only) | `docker compose up` alone yields a working DB (principle 7); re-running is a no-op | Manual step (easy to forget); same in production (replicas would race: production uses a one-off job) |
| Message table stores provenance (model, prompt_ref, tokens, cost, latency, TTFT, trace_id, error_code) | Every answer explainable; Analytics reads Postgres directly | Only Langfuse (couples the UI to the tracing tool) |
| `cost_usd` as `Numeric(12, 8)` | Money summed over thousands of rows must not drift from float rounding | `float` |
| Role enforced by a `CHECK` constraint; cascade delete via `ON DELETE CASCADE` | Integrity enforced by the database itself, even if app code has a bug | App-level validation only |
| `/health/ready` (touches DB) separate from `/health` (no I/O) | Liveness vs readiness: a DB outage should stop traffic, not restart a healthy process | One combined check |
| Eval tables deferred to step 8 as migration `0002` | Keeps each migration about one feature, and shows the second-migration workflow | Put them in 0001 |

## 2026-10-27 · Phase 1 step 4a (streaming chat endpoint)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Chat logic in `services/chat_service.py`, route stays thin | Eval runner and UI run the exact same code; testable without HTTP | Logic inside the route |
| Stream always ends with `done` (outer try/except emits `error` + `done` on anything) | Frontend can rely on one rule to stop spinners; no half-open streams | Let exceptions break the connection |
| Validate model id **before** streaming (HTTP 400); later failures are `error` events | Once the 200 and first bytes are sent the status code can't change | Everything as stream events (worse for API clients) |
| Service opens its own DB sessions inside the generator | A StreamingResponse keeps running after the route returns; request-scoped sessions may be closed by then | `SessionDep` in the chat route (subtle bugs across FastAPI versions) |
| User message committed before the LLM call; partial answers saved with `error_code` | A failed answer never loses the question; partial answers are visible but excluded from the model's history | Save both at the end (a failure loses everything) |
| `LLMError.message` (user-safe) vs `.detail` (logs only) | Users see "No API credit..."; raw provider JSON and request ids stay in server logs | One message for both (leaks provider internals to the UI) |
| History = last 20 user/assistant messages (`chat_history_limit`) | Model APIs are stateless: history is re-sent each turn, so cost and context grow with length | Whole conversation (unbounded); summarisation (Phase 4 memory) |
| SSE headers `Cache-Control: no-cache`, `X-Accel-Buffering: no` | Proxies (nginx in Phase 7) must not buffer or cache a live stream | Defaults (tokens can arrive in one delayed burst behind a proxy) |
| Known limitation: client disconnect mid-stream doesn't save the partial answer | Handled with the Stop button in step 7 (needs cancellation-safe saving) | Solve now (more complexity before there's a UI to need it) |
| Fixed: `"billing"` missing from `LLMErrorKind` (an edit in 3a silently didn't apply) | A step 9 test will assert `LLMErrorKind` ⊆ `ErrorCode` so the two can't drift | — |

## 2026-10-27 · Phase 1 checkpoint A (structured output + Langfuse tracing)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| `LLMGateway.complete_structured(schema=PydanticModel)` via LiteLLM `response_format`, then **re-validate** with Pydantic | Provider-side constrained decoding makes the JSON valid; our own validation means a provider bug surfaces as `invalid_output`, not a crash | Prompt-only "reply in JSON" + parse (fragile); tool-calling tricks to force JSON |
| `reasoning` field first in `IntentClassification` | Models generate left to right; a one-line justification before the label improves accuracy and explains mistakes | Label only (cheaper, less accurate, no explanation) |
| Classifier uses the catalog's **cheap** model by default | Classification will run on every message (Phase 4 routing); it doesn't need the strongest model | Main chat model |
| Langfuse SDK `4.17.0` (not 5.x) | 5.0 is < 14 days old; the 4.x SDK line matches our 4.55 server | Latest 5.0.4 |
| `core/tracing.py` wrapper; no other module imports `langfuse` | Same reason as the LLM gateway: one place to change, and a no-op fallback | Call the SDK everywhere; LiteLLM's built-in Langfuse callback (less control over trace structure) |
| Tracing never breaks the app (missing keys, server down, SDK error = warning + no-op) | Observability is important but must not take chat down with it | Fail requests when tracing fails |
| **Explicit** parent→child observations, `propagate_attributes` only around span creation | Streaming generators pause at every `yield`; "current span" context can leak or break across those pauses | `with start_as_current_observation(...)` spanning the stream |
| One trace per chat turn, `session_id` = conversation id; one generation per model call | Sessions view replays a conversation; each generation has model, params, tokens, cost, TTFT, prompt version | One trace per conversation (unbounded, hard to read) |
| Prompt version recorded as the generation's `version` + metadata | Filterable in Langfuse; Langfuse's native prompt linking needs Langfuse-managed prompts, which we don't use yet | Move prompts into Langfuse prompt management |
| Flush on app shutdown and at the end of scripts | Spans are exported in background batches; a fast exit would drop them | Synchronous export per span (slow) |
| `/api/classify` maps error kinds to HTTP statuses (402 billing, 429 rate limit, 502 invalid output...) | Non-streaming endpoints can and should use real status codes | Always 500 |
| **Per-model `structured_output: native | prompt`**; Ollama Cloud models use `prompt` | Tested 2026-10-27: Ollama Cloud ignores the JSON-schema `format` field for every model tried (even calling Ollama's API directly), so native mode returned plain text. Prompt mode = schema in the system prompt, fence-stripping, Pydantic validation, one retry with the exact validation error | Switch providers just for classification; prompt mode everywhere (wastes native enforcement where it exists) |
| Prompt mode costs ~330 extra input tokens per call (the schema text) | Accepted for Phase 1; Phase 7 cost work can shorten schemas or switch the cheap model to a native-schema provider | — |
| Langfuse v4 API: read traces via `/api/public/v2/observations` | The server runs in v4 "events_only" mode, where the old `/traces` endpoints return 404 | — |

## 2026-10-27 · Phase 1 checkpoint B (frontend shell + chat page)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Browser calls FastAPI directly with **CORS** (origins from `CORS_ORIGINS`) | A Next.js proxy can buffer SSE and kill the token-by-token effect | Next.js rewrites/proxy (same-origin, but buffering risk) |
| Two backend URLs: `NEXT_PUBLIC_API_URL` (browser) and `API_INTERNAL_URL` (server components, Docker network) | "localhost" inside the frontend container is the container itself | One URL (server-side fetches fail in Docker) |
| Own SSE reader (`fetch` + `ReadableStream` + buffer split on blank lines) | `EventSource` can't POST; mirrors our event contract exactly (decision from the Phase 1 plan) | Vercel AI SDK `useChat` |
| Stop = `AbortController`; backend catches cancellation, saves the partial answer as `error_code="cancelled"` inside `anyio.CancelScope(shield=True)` | Inside a cancelled task every await is cancelled again; shielding lets the save finish. `aclosing()` closes nested generators deterministically | Lose partial answers on disconnect (the 4a limitation) |
| `anyio==4.15.1` as a direct dependency | We import it directly now; it was already installed via Starlette | Rely on a transitive dependency |
| BuildKit cache mount for `uv sync` in the backend Dockerfile | Dependency changes no longer re-download all ~85 packages (rebuilds took 10+ min) | Pre-built base image; accept slow builds |
| Routes: `/` = new chat, `/chat/[id]` = conversation (server-rendered history + `loading.tsx` skeleton) | Bookmarkable URLs; history visible before JS loads | Single page with client-side state only |
| New chat creates its UUID on first Send, then `router.replace('/chat/<id>')` after the first answer | Next 16 `cacheComponents` prerenders pages: random values during render would be baked in | Generate in render (rejected by Next), server-generated id |
| Kept Next 16 `cacheComponents: true`; URL-dependent sidebar parts wrapped in `<Suspense>`, Settings model list uses `connection()` inside `<Suspense>` | Static shell is prerendered, live parts stream in. It's Next 16's default model, so we learn it rather than turn it off | Disable cacheComponents (older, fully dynamic rendering) |
| Edited shadcn's `SidebarMenuSkeleton` (useId-based width) and `use-mobile` (useSyncExternalStore) | shadcn code is ours: Math.random() during prerender and setState-in-effect violate Next 16 / React 19 rules | Suppress lint rules |
| `clsx` + `tailwind-merge` in `lib/utils.ts` instead of shadcn's new `cn` package | Approved, mature packages; `cn` was weeks old (it remains a transitive dependency of the shadcn CLI) | `cn` package |
| `shadcn@4.23.0` (published 2026-10-27) as a **devDependency** | 4.21.4 pulled a zod version with a high-severity DoS (npm audit); 4.23.0 fixes it. Only needed at build time (CLI + `shadcn/tailwind.css`) | Keep 4.21.4 (vulnerable); runtime dependency |
| Only messages created during the visit animate in (`live` flag) | History must be visible in server-rendered HTML; `initial={opacity:0}` hid it until JS loaded (caught by a headless screenshot) | Animate everything |
| Atlas theme: cool neutrals + teal accent (OKLCH tokens), same accent as the Atlas Map | A product identity instead of shadcn's default greys | Default theme |

## 2026-10-27 · Phase 1 checkpoint C (evals, tests, docs)

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| Evals call `ChatService.answer()`: same prompt, gateway and tracing as chat, no history, nothing saved to conversations | Measures what users get without filling the sidebar with test chats | Call the HTTP endpoint (pollutes history); call the gateway directly (skips the prompt path) |
| Evals answer with the **chat** model by default; the cheap model is reserved for grading (Phase 3) | Evals must measure the production path | Cheap model (measures the wrong thing) |
| Eval runs in Postgres (`eval_runs` + `eval_results`, migration 0002) + JSON report + Langfuse session per run | Principle 5 (one DB), easy diffing (JSON), drill-down (traces) | Files only |
| Golden set: kebab-case ids, YAML, validated by Pydantic; Acme expected answers define the facts the Phase 2 corpus must contain | Stable ids make runs comparable; validation catches typos before spending money | CSV; free-form questions |
| Baseline (2026-10-27, gpt-oss-120b): GitLab questions answered from general knowledge; Acme questions correctly refused ("don't have that information") | The system prompt's "don't guess company facts" rule works; Phase 2 RAG must turn those refusals into cited answers | — |
| Tests on the host (`uv run pytest`) against `atlas_test`, migrated with Alembic once per session, tables truncated per DB test | Same schema path as production; real Postgres (pgvector) | SQLite; `create_all()` (skips migrations) |
| One event loop per test session (pytest-asyncio config) | The cached async engine's pooled connections are bound to the loop that created them | Per-test loops + engine per test |
| `FakeGateway` via `app.dependency_overrides` | Fast (1.3 s for 39 tests), free, deterministic; asserts on exactly what the model was sent | Mock LiteLLM HTTP calls (brittle) |
| Cross-language drift tests: Python `LLMErrorKind` ⊆ `ErrorCode`, and TS `lib/events.ts` event types + error codes == Python | The contract lives in three places; a test now fails on mismatch (verified by deliberately breaking it) | Code generation from JSON Schema (heavier; revisit if the contract grows) |

## 2026-10-28 · Chat model choice: GPT-OSS 120B vs 20B (Phase 1 exercise 1)

Golden set v1, 20 questions, `chat_system@v1`, one run each on Ollama Cloud:

| Model | Avg latency | Output tokens | Errors | Acme refusals | Notable answer |
| --- | --- | --- | --- | --- | --- |
| `gpt-oss-cloud` (120B) | **1,577 ms** | 5,029 | 0 | 8 / 10 | MVC → "Minimum Viable Change" (close; handbook says Minimal *Valuable* Change) |
| `gpt-oss-20b-cloud` (20B) | 2,533 ms | 4,408 | 0 | 8 / 10 | MVC → asked if it meant Model-View-Controller (wrong) |

Reports: `backend/evals/results/20261028-045212_b7fb4019.json` (120B), `20261028-045400_004f893f.json` (20B).

- **Decision:** keep **120B** as the default chat model. It was faster in this run and gave the better answer on the one question where quality visibly differed.
- **Why the bigger model can be faster:** both are mixture-of-experts models that use only a few billion parameters per token, so size barely affects speed; provider load and how long each model "thinks" dominate. Input tokens were identical (4,061), so the difference is entirely model-side.
- **Caveats:** one run per model is a small sample (cloud latency varies run to run; 2–3 runs each would be fairer). Correctness isn't scored yet: "better answer" is a manual reading of a few answers. Phase 3's LLM-as-judge replaces that with a score.
- **Alternatives:** 20B as the default for cost (no per-token price on Ollama Cloud, so no saving today); Claude Sonnet 5.5 once the account has credit (re-run this comparison then).
- **Keep 20B as the cheap model** for classification, where both are fast enough and the task is simpler.

## 2026-10-29 · Chat prompt v2: length cap + follow-up question (Phase 1 exercise 2)

`chat_system@v2` adds one rule to v1: "Keep answers under 120 words and end with one suggested follow-up question." Golden set v1, 20 questions, `gpt-oss-cloud` (120B), one run each:

| Prompt | Avg latency | Input tokens | Output tokens | Errors | Follow-up question | Over 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| `chat_system@v1` | 1,577 ms | 4,061 | 5,029 | 0 | — | — |
| `chat_system@v2` | 1,588 ms | 4,381 (+8%) | **4,295 (−15%)** | 0 | **20 / 20** | 5 / 20 (longest 151) |

Reports: `20261028-045212_b7fb4019.json` (v1), `20261029-132505_ee5684e0.json` (v2).

- **Decision:** keep **v2** active. Answers are shorter and every one invites a next step, at no latency cost.
- **Prompt rules are soft:** the 120-word cap was broken 5 times. A hard limit needs `max_tokens` or a post-generation check; the prompt only nudges.
- **Shorter answers weren't faster:** latency is dominated by time to first token and the model's hidden reasoning, not the length of the visible answer.
- **Every prompt line is paid on every call:** +16 input tokens per question here; small, but it scales with traffic and history.
- **Caveats:** one run each; answer quality not scored yet (Phase 3 LLM-as-judge). The UI small print doesn't show the prompt version; it is in the `done` event, the database and Langfuse.
- **Alternatives:** stay on v1 (longer, more complete answers); enforce length with `max_tokens` (can cut answers mid-sentence).
