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

## 2026-10-30 · Phase 2 checkpoint A: knowledge base ingestion

| Decision | Why | Alternatives |
| --- | --- | --- |
| Local embeddings: `sentence-transformers` 6.1.0 + `BAAI/bge-small-en-v1.5` (384 dims), CPU-only `torch` 2.14.1 from PyTorch's CPU index on Linux | Free, offline, fast enough on CPU for ~850 chunks; small vectors keep the index small. CPU index avoids GPU libraries in the image | `bge-base` (768 dims, slower, maybe better: exercise); `fastembed` (no torch, less standard); API embeddings (cost, network) |
| `core/embeddings.py` as an embedding gateway with an `Embedder` interface; model lazy-loaded on first use | Same reasoning as the LLM gateway: one place to swap models; tests inject `FakeEmbedder`; API startup stays instant | Calling sentence-transformers directly from ingestion and retrieval |
| BGE query prefix ("Represent this sentence for searching relevant passages: ") on queries only | BGE was trained that way; improves retrieval of passages for short questions | No prefix |
| Heading-aware recursive chunker: headings → paragraphs → sentences → word windows; 350 tokens, 50 overlap, merge chunks under 40 tokens | Keeps passages on one topic and records the heading path; never cuts a paragraph that fits. Real corpus: median 143 tokens, max 381 incl. header (< 512 BGE limit) | Fixed-size windows (cuts mid-sentence); semantic chunking (Phase 3 comparison) |
| Contextual chunk headers: embed `"<title> / <heading path>\n\n<text>"`, store clean text | A passage like "up to 5 days carry over" needs its context ("Time Off Policy / Vacation") in the vector to match questions | Embed raw chunk text only |
| `documents` + `chunks` tables (migration 0003), `vector(384)`, HNSW index with `vector_cosine_ops`; chunks replaced per document in one transaction | Principle 5 (one DB); HNSW avoids scanning every row; searches never see half-updated documents | IVFFlat (needs training on existing data); a separate vector DB (Pinecone, Qdrant) |
| Re-ingestion skips documents by sha256 content hash; sources prune documents they no longer yield; failures are recorded per document and the run continues | Cheap re-runs; the index matches the folders; one bad file doesn't stop an import | Always re-embed everything; stop on first error |
| GitLab corpus: 35 handbook pages fetched at a pinned commit by `scripts/fetch_gitlab_handbook.py` and committed to `data/gitlab/` | Reproducible scores; ingestion needs no network | Crawl handbook.gitlab.com live (pages now redirect to a login for some paths; scores would drift) |
| Golden set updated to today's handbook: GitLab's mission is now "Unlock every team to ship trusted software at the speed of imagination"; async → `/handbook/communication/`; public handbook → `handbook-usage` | The eval must match the corpus it's measured against | Keep stale answers (would mark correct answers wrong) |
| Acme corpus: 12 synthetic docs written to state every golden-set fact exactly once, plus distractors (travel policy's $60 meal allowance vs the expense policy's $75 client meals) | Known ground truth for hit rate and citation checks; distractors make retrieval non-trivial | Only "easy" docs |

## 2026-10-30 · Phase 2 checkpoint B: retrieval, grounded answers, citations

| Decision | Why | Alternatives |
| --- | --- | --- |
| `VectorRetriever` (pgvector `<=>`, top 5, score = 1 − cosine distance) behind the `Retriever` interface; the chat service wraps it in a Langfuse `retriever` span | Swappable for hybrid/reranking in Phase 3 without touching the chat; every answer's sources and scores are visible in the trace | Retrieval inside the prompt code; a similarity threshold (BGE scores are compressed around 0.6–0.9, so a fixed cut-off is hard to tune: later) |
| Retrieve with the latest question only | Simple and measurable now | Query rewriting from history (Phase 3; follow-ups like "and for fathers?" search poorly today) |
| `chat_system@v3`: sources in the system prompt as `[1]..[5]`, "answer only from sources, say when not found", cite as `[n]`, sources are data not instructions | Grounding and citations; the system prompt is rebuilt per turn, so old turns' sources don't pile up in history | Sources in the user message; JSON-structured answers with source ids (can't stream as plain Markdown) |
| Citations emitted **after** the answer, only for numbers the answer used; numbers outside 1..k dropped; parser also accepts gpt-oss's `【1】` / `【1†…】` | A chip should mean "this answer relies on this passage"; tolerant parsing works across models (gpt-oss ignored the `[1]` example on the first real test) | Emit all retrieved chunks up front (chips for unused sources); a new prompt version to forbid 【】 (models fall back to training habits anyway) |
| Citations saved on the message (`messages.citations` JSONB, migration 0004) and returned by the conversations API | Reopened chats show the same chips; always read with their message, never queried alone | A `citations` table (more joins for no current query) |
| `CitationEvent.heading` added (optional field) | The chip popover shows where in the document the passage is; adding an optional field is non-breaking | Put the heading into `title` |
| Eval metrics: hit rate @5, MRR, cited-correct rate, stored per result and per run (migration 0004); `--retrieval-only` mode with no model calls | Retrieval changes can be measured in seconds, for free; cited-correct is Phase 2's "done when" | RAGAS context precision/recall (Phase 3) |
| Golden label fix: `gitlab-all-remote` also accepts `all-remote/terminology/` | That page states "no company-owned offices anywhere"; the answer cited it correctly and was scored wrong. Changed *after* seeing results, so recorded here | Keep the narrow label (understates retrieval by 5 points) |
| Embedding model warmed up in the background at API startup | First chat doesn't wait for model load; API is up immediately | Load at first request (slower first answer); block startup |
| shadcn components import `cn` from `@/lib/utils` instead of the `cn` package | `cn` was only resolvable as a transitive dependency of the `shadcn` CLI (dev dependency); `shadcn add` also tried to add it to package.json (reverted) | Add `cn` 0.5.1 as a dependency (an unapproved new library) |

**Results** (gpt-oss-120b, 20 questions, run `6714fe10`): hit rate 90%, MRR 0.77, **cited correct 90%** (target 80%), 0 errors, avg latency 1.1 s, ~1,025 input tokens per question (was ~220 without sources). After the label fix, retrieval-only: hit rate 95%, MRR 0.82. Remaining miss: `gitlab-mvc`; the model correctly said it couldn't find it instead of guessing (acronym; Phase 3 hybrid search).

## 2026-10-30 · Phase 2 checkpoint C: Knowledge Base page

| Decision | Why | Alternatives |
| --- | --- | --- |
| Uploads are a `DataSource` (`UploadSource`) over a folder in a Docker volume (`uploads`), listed in `config/rag.yaml` | `ingestion.run --force` re-embeds uploads like everything else; deleting the file prunes the document on the next run | Store upload bytes only in Postgres (re-embedding would need a separate path); write into `data/` (read-only in the container, and committed to git) |
| Upload returns 202 with status `pending`; ingestion runs in a FastAPI `BackgroundTasks` task; the page polls every 1 s while anything is pending/processing | Long PDFs take seconds to minutes; the request must not wait. Background tasks need no extra infrastructure | Redis job queue (retries, multiple workers: Phase 7 if needed); pushing progress over SSE |
| Upload checks: extension allow-list and size limit from `rag.yaml` (10 MB), empty files rejected, file names sanitised to `[A-Za-z0-9._-]` and stripped of directories | Never trust a client-supplied file name (path traversal); only formats we can parse | Content sniffing by magic bytes (stronger; worth it once uploads come from outside the team) |
| Only uploaded documents can be deleted from the UI | GitLab/Acme documents come from `data/` and would reappear on the next ingestion run | Allow deleting anything (confusing) |
| Document ids travel as query parameters (`?document_id=`) | Ids contain `:` and `/` | Path parameters with URL-encoding (fragile with proxies) |
| `GET /api/knowledge/config` serves upload limits, top-k and the embedding model to the page | Principle 8: the UI reads config instead of duplicating it | Hard-code `.md,.pdf,...` in the frontend |
| Retrieval tester on the page (`GET /api/knowledge/search`, no LLM) | Shows exactly which passages the chat would get, with scores; free and instant for debugging | Only look at Langfuse traces |
| `app/knowledge/loading.tsx` as the Suspense boundary | Next 16 (cacheComponents) warns when request-time data is read outside Suspense; the header and skeleton now render instantly | `export const instant = false` (blocking page) |

## 2026-10-30 · Phase 3: advanced RAG + evals (built in one shot at my request)

| Decision | Why | Alternatives |
| --- | --- | --- |
| Golden set v2: 50 questions, 30 new ones tagged `keyword`, `follow-up` (with `history`), `relational`, `paraphrase`, `unanswerable`; new doc `acme-docs:company/teams-and-people.md` (org chart) | Phase 2 scored 95% on the old 20, leaving no room to show a gain; categories show *where* a change helps | Keep 20 questions; untagged questions |
| Keyword search = Postgres full-text (`chunks.search_vector`, GIN index, migration 0005, backfilled) for candidates + BM25 computed in Python | Postgres' `ts_rank` has no IDF (a rare "mvc" counts like a common "gitlab"); BM25's numbers all come from the candidate rows, so no second index to keep in sync | `ts_rank_cd` only; `rank_bm25` library (a new dependency, an in-memory index to invalidate); Elasticsearch/OpenSearch (a new service) |
| `search_vector` built from title + heading + text at ingestion, not a generated column | A generated column can't read the documents table's title | Generated column on heading + text only (loses title matches) |
| Hybrid = Reciprocal Rank Fusion (k=60) over 20 candidates per retriever, score normalised to 1.0 = "first everywhere" | Scores from different retrievers aren't comparable; ranks are | Weighted score sum (needs per-retriever normalisation and tuning) |
| Reranker: `BAAI/bge-reranker-base` re-scores the top 10, **not in the chat path** (`hybrid_rerank` is opt-in) | MiniLM-L6 was 5x faster but *lowered* paraphrase MRR (0.49 → 0.43); BGE raised it to 0.75, but costs ~1.5–3 s per question on CPU for +0.01 overall MRR | Rerank in chat (slower answers); ONNX/quantised reranker (new deps); GPU |
| Query rewriting with the cheap model, only when there are earlier turns; `query_rewrite@v2` keeps the user's wording | v1 wrote keyword lists ("Acme Corp sick days") whose company name matched every Acme chunk (a follow-up went from #1 to a miss); v2: follow-up MRR 0.81 → 1.00 | Always rewrite (cost, latency); HyDE; send the whole history to the embedder |
| GraphRAG: Neo4j 5.26 community + `neo4j` 6.4.1 driver; LLM extraction per section into a fixed vocabulary (7 entity, 11 relation types); entities merged by normalised name; every relation keeps its document + evidence sentence; Acme only | Multi-hop questions ("lead of the team that owns X") need explicit links; fixed types keep Cypher reliable and safe to format; per-section extraction because one reply for the org chart overflowed the output limit (invalid JSON) | Microsoft GraphRAG (community summaries; heavy); Postgres link tables (recursive CTEs); free-form relation types |
| Graph search: full-text entity match (seeds ≥ 75% of the best score, Company skipped), walk ≤ 2 hops not through the company node, dedupe facts, one chunk per source document; used as a third RRF list (`hybrid_graph`, the chat default) | Facts are cited like passages; no effect when a question names no entity; Neo4j down → graph returns nothing, chat keeps working | Graph-only answers; separate "graph mode" toggle |
| LLM judge in-house (`evals/judge.py`, `eval_judge@v1`): RAGAS definitions (faithfulness, answer correctness, context precision) in one structured call per question, cheap model, through the gateway | `ragas` calls models outside our gateway (no tracing/cost) and relies on schema enforcement Ollama Cloud ignores; one call keeps cost at 50 cheap calls per run | `ragas` library (approved in the plan, not added); 3 separate judge calls (more isolated, 3x cost) |
| CI (GitHub Actions): ruff + pytest on pgvector, eslint + tsc, then a retrieval-only eval with real embeddings that fails below hit rate 93% / MRR 0.80 | Free and deterministic, so it can gate every PR; judged evals cost money and vary, so they run on demand | Full judged evals in CI (needs API key secrets, flaky) |
| Embedding map: t-SNE (scikit-learn 1.9.1, already installed via sentence-transformers, now pinned explicitly), cached until chunks change | Clear topic clusters; no new library | PCA (muddier clusters, but can place a query point); UMAP (one more dependency with numba) |
| UI: React Flow 12.12.0 (graph explorer, client-only render, own force layout), Recharts 3.10.1 (map, analytics) | Both in the planned stack; React Flow measures nodes in the browser, so server-rendered positions can't match (hydration warning) | d3-force (one more dependency); server-side layout |

**Results** (50 questions, gpt-oss-120b answers, gpt-oss-20b judge). Baseline run `327d000b` (vector, no rewriting) → Phase 3 run `1c367b78` (hybrid_graph + rewriting v2): hit rate 89% → **96%**, MRR 0.81 → **0.87**, cited correct 83% → 89%, answer correctness 72% → 76%, faithfulness 88% → 94%, follow-up correctness 42% → 83%, latency 1.39 → 1.53 s. Relational (75 → 69%) and unanswerable (100 → 75%) dropped on judge noise: near-identical answers got 1.0 in one run and 0.0 in the other. Per-category numbers on 4–8 questions are within the judge's noise.

Retrieval-only (46 scored questions): vector 89% / 0.809 · keyword 91% / 0.767 · hybrid 96% / 0.847 · hybrid_rerank (BGE) 96% / 0.856 · hybrid_graph 96% / 0.847.

## 2026-10-31 · Phase 4 part A: agent, tools, human approval

| Decision | Why | Alternatives |
| --- | --- | --- |
| LangGraph 1.2.16 for orchestration only; every model call still goes through our gateway (`LLMGateway.complete_with_tools`, LiteLLM tool calling) | Principle 2 (tracing, cost, model switching stay in one place); LangGraph gives interrupts + checkpoints without its LLM wrappers | LangChain chat models inside LangGraph (bypasses the gateway); a hand-written loop (no durable pause/resume) |
| Routing with the Phase 1 intent classifier: `action_request` → agent, everything else → the existing RAG path (`config/agent.yaml`) | Plain questions stay fast (one model call); classifier failure falls back to RAG ("answering is safer than acting") | Agent for every message (slower, more tokens); keyword rules |
| Tools implement the existing `Tool` interface: `search_docs`, `query_org_chart`, `calculator` (read, run at once); `create_ticket`, `post_slack_message` (`requires_approval`) | Interfaces before implementations; Phase 5 MCP tools plug into the same interface | Tool functions defined ad hoc in the agent |
| Writes pause with LangGraph `interrupt()` in a side-effect-free `approval` node; approved writes run in the next node (`act`) | A resumed node re-runs from the start: side effects before the interrupt would happen twice | Interrupt inside the tool itself (double execution on resume) |
| Checkpoints in Postgres (`langgraph-checkpoint-postgres` 3.2.0 + `psycopg` 3.3.6) in schema `langgraph`, opened in the app lifespan | Paused runs survive restarts (uvicorn reloads on every save); own schema so Alembic never touches LangGraph's tables | In-memory saver (lost on reload); Redis |
| One LangGraph thread per agent turn; approval id = `<thread>/<tool call id>`; resume checks the conversation and that this exact approval is pending | No extra table; a stale, replayed or foreign approval gets 404 (replay test: no second ticket) | Thread per conversation (agent state diverges from RAG turns) |
| Paused turns are saved as an assistant message (`error_code=awaiting_approval`, steps/tool calls/approvals in `messages.agent` JSONB, migration 0008); resume updates the same message | A reload or reopened chat still shows the approval card; history skips the paused message | Keep pending approvals only in the browser (lost on navigation: found in the first UI test) |
| Simulated Jira/Slack: `sim_tickets`, `sim_slack_messages` (migration 0007) + an Outbox page | No real company systems touched in development; the approve-then-act flow is real | Real Jira/Slack sandboxes (credentials, flaky demos) |
| Agent answers aren't token-streamed: the decision call returns whole text, sent as small token events | Tool-calling replies must be complete before acting; same event contract as RAG | Streaming tool-call deltas (more complex parsing for little gain) |
| New `ToolCallEvent.summary` (optional) mirrored in `events.ts` | Humans read "Create a high-priority IT ticket: …", not JSON; optional = non-breaking | Build summaries in the frontend per tool |

## 2026-10-31 · Phase 4 part B: memory, activity panel, agent evals

| Decision | Why | Alternatives |
| --- | --- | --- |
| Short-term memory: newest 10 messages verbatim + a running summary (cheap model) stored on the conversation, folded in batches of 10 (migration 0009, `config/memory.yaml`) | Fixed prompt size for long chats; one summary call per 10 messages, not per turn | Sliding window only (forgets early facts); summarise every turn (cost, latency) |
| Long-term memory: after each turn a background task extracts lasting user facts (cheap model, structured output), embeds them with BGE, skips near-duplicates (cosine ≥ 0.9); top 5 recalled per message into `$memory` | Facts survive across conversations; the answer never waits for extraction | Store whole conversations as memory (noisy); a separate memory service (Mem0, Zep: new dependency) |
| Memories are listed and deletable in Settings (`/api/memories`) | The user's data; a wrong fact would silently shape every answer | Invisible memory |
| Single-user memory for now | No login until Phase 7, which adds `user_id` | Fake per-browser ids |
| Prompts: `chat_system@v4` and `agent_system@v2` add `$memory`; `agent_system@v3` adds "act when the request has what the action needs" after an eval miss | Prompt changes are versioned and tied to an eval result | Edit v2 in place (old traces would lie) |
| Agent log gets a timestamped `timeline`; the Agent Activity Panel (chat header) shows memory, routing, thinking steps, tool calls with input/output, approvals | Every agent step visible live (the Phase 4 UI goal); saved, so it survives reloads | Only Langfuse (not visible to users) |
| Agent evals (`evals/agent_tasks.yaml`, `python -m evals.agent_run`): routing accuracy, action accuracy (tool + key args), and an approval gate checked with spy write tools that fail the run if called; every proposal is rejected | Safety is tested, not assumed; nothing is ever written during evals | Judge the final answer text only; LLM-judged action quality (later) |

**Agent eval results** (gpt-oss-120b, 12 tasks): routing 100%, action accuracy 88% (7/8), unapproved writes 0, ~2.5 model calls and ~3.9 s per action. The miss (`vpn-slack`: asked a clarifying question instead of posting) persisted after `agent_system@v3`, then passed 3/3 when re-run alone: temperature 0.7 makes agent decisions vary. Next fix: a lower temperature for the agent only (Phase 4 exercise 2).

## 2026-10-31 · Phase 5 part A: the agent team + animated graph

| Decision | Why | Alternatives |
| --- | --- | --- |
| Four agents behind the `Agent` interface: Planner (plans, then writes the answer), Researcher (read tools only), Action (writes + org chart), Verifier (checks the draft); `agents/team.py` | Narrow prompts and toolsets per role; each is testable and evaluable alone | One agent with all tools (Phase 4, still available: `mode: single` in `config/agent.yaml`) |
| Supervisor pattern: the Planner's plan is made once, a `dispatch` node hands each step to a specialist; specialists never call each other | Predictable, bounded order of work that is easy to show in the UI | Handoff/swarm pattern (agents pass control directly: flexible, harder to bound and follow) |
| Per-specialist scratchpad: append-only `work` + `work_start` index | A specialist sees only its own task (+ earlier findings as notes), not other agents' tool chatter | Shared message list (prompts grow, roles blur) |
| Shared node builders (`agents/nodes.py`) for tools / approval / act, used by both graphs | One implementation of the approval safety rule | Copy the nodes into the team graph |
| Verifier runs on every action request; may send the draft back once; the final answer is delivered after one revision either way | "Checks its own work" for the demo; bounded cost (user chose "always") | Verify only when sources were used; unlimited revision loops |
| Specialists capped at 3 model calls per step (`MAX_TURNS_PER_STEP`) + team budget 14 | Agent eval showed a researcher searching 7 times for a fact no document has | Only the global budget (one bad step starves the rest) |
| Prompt fixes from evidence: `team_planner@v2`, `team_researcher@v2`, `team_action@v2` (shared facts: Jira projects IT/HR/FIN/SEC, channels from the org chart), `team_verifier@v2` (judge against the user's request, not everything a policy suggests), `memory_extract@v2` (no one-off events or trivia) | Each fix is tied to an observed failure (live run or eval) | Bigger model; few-shot examples everywhere |
| Animated agent graph (React Flow) in the Activity panel, derived from the saved timeline (`lib/agent-graph.ts`) | Handoffs visible live and in reopened chats, from one source of truth | A separate events stream for the graph |

**Agent evals, single vs team** (gpt-oss-120b, 12 tasks): routing 100% / 100%; action accuracy 88% / 88% (team was 25% before the prompt v2s and the step cap); unapproved writes 0 / 0; model calls 2.5 / 6.1; latency 4.4 s / 10.0 s. Same accuracy at ~2.5x cost: the team buys verification and visible handoffs, not accuracy, on these tasks. `vpn-slack` fails in both modes (the model asks for details it was given): a model behaviour to fix with a lower temperature (Phase 4 exercise 2).

## 2026-10-31 · Phase 5 part B: MCP

| Decision | Why | Alternatives |
| --- | --- | --- |
| Official MCP Python SDK `mcp` 2.3.0 (+ `jsonschema` 4.26.0 pinned explicitly; new transitive deps: `httpx2`, `mcp-types`, `pyjwt`, `sse-starlette`, `cryptography`) | Current major version; `MCPServer` (renamed from FastMCP), a unified `Client` that also connects in-process (tests) | `mcp` 1.30 (older API on httpx 0.x); hand-written JSON-RPC |
| Simulated Jira and Slack as Streamable HTTP MCP servers in their own containers (`mcp-jira`, `mcp-slack`, same image as the backend); host check allows the Docker service names | Realistic separation (a real Jira MCP server would be another service); config change to swap | stdio subprocesses inside the backend; keep direct Python tools |
| Atlas as an MCP client: discover tools at startup (retries), wrap each as `McpTool` (JSON Schema validation via `parse_arguments`), call the server per tool call; fall back to built-in simulated tools if a server is down | Agents see one `Tool` interface; tool names match the old ones, so prompts and evals didn't change | Long-lived sessions (state to manage); fail hard when a server is down |
| Default-deny approval: every MCP tool needs approval unless `config/mcp.yaml` lists it under `read_only_tools`; server annotations are ignored for that decision | A server's "read-only" label is its own claim; the trust decision belongs to Atlas | Trust `readOnlyHint` annotations |
| Atlas as an MCP server over stdio (`python -m mcp_servers.atlas`) with read-only tools only: `search_knowledge_base`, `query_org_chart`, `ask_atlas` | Claude Desktop launches local servers as commands; writes stay behind Atlas's approval UI | Expose write tools (bypasses approval); HTTP endpoint (auth needed) |
| `Tool.definition()` / `json_schema()` became instance methods; `Tool.parse_arguments()` + `ToolArgumentError` | MCP tools get their name and schema at runtime, per instance | A Pydantic model generated from JSON Schema per MCP tool |
| `team_writer@v2`: no [n] when there are no sources | Seen live: "[1] Action completed by the team" with no sources | — |

**Verified:** both servers discovered over HTTP in Docker (4 tools); an approved agent ticket created through MCP (HR-1001); Atlas's MCP server over stdio via `docker compose exec` (as Claude Desktop does): tool list, search, and a cited `ask_atlas` answer. Claude Desktop itself not tested here (exercise 3). A test caught a bug: optional arguments the model leaves out (priority) broke the approval summary; defaults now come from the schema.

## 2026-11-05 · Phase 6 checkpoint A: questions about images

| Decision | Why | Alternatives |
| --- | --- | --- |
| Vision model: Gemma 4 31B on Ollama Cloud (`gemma4-cloud`, `defaults.vision` in `config/models.yaml`); Claude Sonnet/Haiku marked `vision: true` for later | Tested 2026-11-05 with a real screenshot: correct answer in 2.1 s, ~300 input tokens, inside the free tier. Claude still returns "credit balance too low"; Mistral Large and Kimi need paid Ollama credits | Claude Sonnet (best quality, needs credit); a local vision model in Ollama (no local Ollama running) |
| Routing by capability: a message with images goes to `defaults.vision` when the chosen model has no `vision` flag; the UI gets a "Switched to a vision model" step. The gateway also refuses images for a text-only model (`bad_request`) as a safety net | A text-only model either errors or silently ignores the image and answers as if it weren't there | Grey out text-only models when an image is attached (more UI, same effect) |
| Describe, then search: the vision model writes a ≤120-word description (`image_describe@v1`: kind of image, all visible text, chart values); it joins the search query and is stored with the image | Search needs words; a screenshot's titles, labels and numbers are what match documents. Stored descriptions let follow-ups refer to the image as text | Image embeddings (CLIP/SigLIP) in the same index (needs a second embedding model and space); ColPali page embeddings; search with the question only (misses what's in the image) |
| The answer model reads the image itself plus the sources; `chat_system@v5` adds one rule: say when a fact comes from the user's image, cite [n] only for facts from sources | The description is lossy; the answer should use the real image. Keeping "seen in your screenshot" apart from cited facts keeps citations honest | Answer from the description only (cheaper, loses detail) |
| Earlier turns' images are re-sent as text (`[Attached image: <description>]`), only the current question's images as images | An image costs hundreds of tokens on every turn it's re-sent | Re-send all images (cost grows with the chat) |
| Images go straight to the RAG path, skipping the agent router | The agent's tools are text-only; an image question is a question | Route as usual (the agent would ignore the image) |
| Storage: `message_images` table (bytea, migration 0010), served by `GET /api/images/{id}` with `nosniff` and long caching; real type sniffed from magic bytes, never the browser's label; limits in `config/multimodal.yaml` (3 per message, 5 MB) | Principle 5 (one database); small files, read with their message, deleted with it (cascade) | Files in a Docker volume; MinIO/S3 (another service for Atlas) |
| Base64 images are replaced by `[image: type, size]` in Langfuse inputs | Traces stay readable and small; no image data in the trace store | Upload images as Langfuse media |

**Verified live:** a screenshot of the meal-allowance answer, asked with GPT-OSS selected → switched to Gemma 4 → described (text read correctly) → hybrid search found the Expense Policy → answer kept "your screenshot shows $60" apart from the cited $75 client-meal rule [2]; 5.5 s, 1,295 input tokens. In the browser: picked file → thumbnail → answer about an approval-card screenshot citing the Hardware Policy; the image reloads from the API.

## 2026-11-08 · Phase 6 checkpoint B: scanned PDFs and images in the knowledge base

| Decision | Why | Alternatives |
| --- | --- | --- |
| Convert to text at import time: a vision model transcribes scanned pages (`ocr_page@v1`) and describes images (`image_index@v1`); the text is then chunked, embedded and cited like any document | Retrieval, reranking, citations and evals all work unchanged; one vision call per page, once, instead of on every question | Embed page images directly (ColPali, CLIP): keeps layout, but needs a second index and embedding model, and answers would need images at question time |
| Only pages with no text layer are rendered and OCR'd (`pypdfium2` 4.30.1, grayscale at 150 DPI); typed pages keep their text | A mixed PDF pays only for its scanned pages; pypdf's text layer is exact, OCR may not be | OCR every page (slower, can introduce errors); Tesseract (another system dependency, weaker on tables and charts) |
| A 20-line PNG encoder (`encode_gray_png`) instead of adding Pillow | One small function; no new dependency for one format | Pillow (approval needed, much bigger) |
| OCR prompt: verbatim, Markdown headings, `[unreadable]` instead of guessing; image prompt: every chart value as a Markdown table | The chunker splits on headings; questions like "how many hardware tickets?" need the exact number in a chunk, not just "hardware was second" | Free-form description (loses values) |
| A scan or image takes its title from the first `# ` heading the model transcribed, not the file name | "Office Access and Visitor Policy" beats "office-access-policy-scan" in citations and search | File name (what the source gives) |
| Limits in `config/multimodal.yaml` (`ingestion.render_dpi`, `ingestion.max_ocr_pages: 20`); one Langfuse trace per document (`ingest_vision`) | Cost control and visibility for a 300-page scan | No limit |
| Upload image types (`.png .jpg .jpeg .webp`) in `config/rag.yaml`; the bytes are sniffed, so a renamed text file is refused (415). The Acme source also loads `.pdf`/`.png`/`.jpg`. The graph build skips scans and images | The extension is a claim; graph extraction would pay for OCR a second time | Separate image source; OCR during graph build too |
| Golden set v3: 5 `multimodal` questions whose answers exist only in pixels (fixtures: a scanned Office Access policy PDF with no text layer, an IT tickets bar chart; both rendered from HTML) | The eval only passes if the vision model read them at import | Hand-check only |

**Verified live:** `ingestion.run` OCR'd the scan word for word (3.5–11.8 s) and turned the chart into a table with all 5 values (1.7–2.1 s). Multimodal evals (answers by `gpt-oss-cloud`, chat_system@v5): hit rate 100%, MRR 1.0, cited correct 100%, faithfulness 100%, correctness 90% on both runs (a different question scored 0.5 each time: the judge wanted extra facts that weren't asked; after the first run I removed one such fact from the badge question's expected answer). In chat: "I lost my badge…" → 24 hours, first replacement free, then €25 [Office Access and Visitor Policy]. An uploaded phone-style JPEG of the memo became a ready document; a fake `.png` got 415.

## 2026-11-08 · Phase 6 checkpoint C: voice

| Decision | Why | Alternatives |
| --- | --- | --- |
| Speech-to-text: local Whisper via `faster-whisper` 1.2.1 (CTranslate2, int8 on CPU), model `base`, in `core/speech.py`; endpoint `POST /api/voice/transcribe` | Free, private (audio never leaves the backend), ~1 s per question on a laptop CPU. Not an LLM call, so it sits beside the gateway like embeddings, with its own Langfuse trace (`transcribe`) | OpenAI/Groq Whisper APIs (cost, audio leaves the machine); the browser's Web Speech recognition (Chrome sends audio to Google; Firefox has none) |
| `av` pinned to 15.1.0, not the latest 19.0.2 | av 19 removed the `metadata_errors` argument that faster-whisper 1.2.1 passes: every decode failed | Wait for a faster-whisper release |
| `base`, not `small` (measured, 6 clips): base WER 7.7%, ~1 s per clip; small 9.1% and ~3 s, real-time factor 1.11 (slower than speech) | Bigger wasn't better on clean speech, and 3x slower | `small`/`medium` for accents and noisy rooms (re-measure with real recordings) |
| Initial prompt "Acme employees asking Atlas about GitLab, Jira and Slack." (`voice.prompt`): WER 7.7% → 3.8%, and "age era ticket" → "Jira ticket" | Whisper's decoder continues from the prompt, so it expects these spellings. A comma-separated glossary made it worse (17.3%: it copied the capitals, "Water GitLab's Core Value"); a sentence with people's names 9.6%; `hotwords` 13.5%. **Caveat:** 6 synthetic clips, so this may be tuned to them | Fine-tune Whisper on company audio (Phase 8 territory); post-correct with an LLM |
| Voice-activity filter on (`vad_filter`, Silero VAD) | Trims silence first; Whisper otherwise sometimes invents words in silence | Off (a little faster) |
| The transcript goes into the message box, not straight to the chat | Speech recognition makes mistakes; you check and fix before asking | Send immediately (faster, but sends errors) |
| Text-to-speech in the browser (`speechSynthesis`): a speaker button on each answer; answers to questions asked by voice are read aloud automatically. Markdown, citation markers and URLs are stripped first (`toSpeakable`) | Free, instant, offline, no backend work; voices come from the OS | Server TTS (Piper, Kokoro; better voices, another model); cloud TTS (cost) |
| Limits in `config/multimodal.yaml` (`voice.max_seconds: 60`, `max_mb: 10`), mirrored in the frontend's auto-stop | One long recording can't tie up the CPU | — |
| Voice eval `python -m evals.voice_run`: word error rate on 6 spoken questions (macOS `say`), plus real-time factor | The number to compare model sizes and prompts with; synthetic speech is a floor, not real-world accuracy | Real recordings (exercise) |

**Verified live:** in Chrome, with the page's microphone replaced by a stream playing a clip (headless Chrome on macOS ignores `--use-file-for-fake-audio-capture`), the real recorder, waveform, upload, Whisper and auto read-aloud ran end to end. The plan's "Done when" check: a spoken "Which policy covers the repair in my screenshot?" with an approval-card screenshot attached → transcribed exactly → routed to Gemma 4 (image described) → "covered by the Hardware Policy [1]", read aloud. Test conversations deleted.

## 2026-11-13 · Phase 7 checkpoint A: guardrails

| Decision | Why | Alternatives |
| --- | --- | --- |
| Three layers (defence in depth): quarantine at ingestion, prompt rules (`chat_system@v6`), output check after the answer | Each layer misses things the next can catch; no single filter is reliable against injection | One strong filter; NeMo Guardrails / Llama Guard as a separate service |
| Layer 1 at **ingestion**, per chunk: regex heuristics as hints + the cheap model as classifier (`injection_scan@v1`, 8 passages per call, each fenced in `<passage>` tags). Suspicious chunks are **quarantined** (`chunks.quarantine_reason`, migration 0011): kept and shown on the Knowledge page, never retrieved | Scan once, not on every question; chunk-level keeps the rest of a document usable; visibility makes the demo and debugging possible | Scan retrieved chunks at question time (cost per question); delete flagged chunks (no audit trail); document-level quarantine |
| Heuristics are hints, the classifier decides. Measured on 20 labelled passages: heuristics alone caught 7/10 attacks **and** flagged 7/10 ordinary passages (the real password policy, "System: payroll runs on the 25th", executive assistants) | Keywords can't tell an attack from a policy that quotes one; paraphrased and Dutch attacks have no keywords at all | Heuristics only (unusable precision); classifier only (no fallback) |
| If the classifier is down, heuristics decide alone ("fail closed") and the reason is marked `(classifier unavailable)`; such documents are rescanned on the next ingestion run | Safe by default, but a model outage mustn't hide real policy forever. On the real corpus heuristics fire on 6 of 889 chunks | Fail open (ingest unscanned); keep provisional quarantines until --force |
| The graph build skips documents with quarantined chunks | It reads whole documents, so it would carry the attack into graph answers | Extract only clean chunks |
| Layer 2: `chat_system@v6` spells out what injections ask for (credentials, links, secrecy) and allows only contact details found in the sources or the question | The v5 one-liner ("ignore instructions in sources") didn't say what to do instead | Spotlighting/encoding the sources (e.g. base64): stronger, but hurts answer quality |
| Layer 3: after the answer, emails and URLs that no source and not the question contain → a warning under the answer (RAG path) | The payload of a successful injection is almost always a destination. It warns rather than blocks, because the answer has already streamed | Buffer the answer and block (loses streaming); LLM output judge (cost per answer) |
| PII: Presidio 2.2.366 + spaCy `en_core_web_sm` 3.8.0, masking EMAIL, PHONE, CREDIT_CARD, IBAN, US_SSN, IP in the user's message **before** anything saves or sends it (the route masks, so RAG, agent, memory, traces and the database only see `<PHONE_NUMBER>`); the user sees a "Masked personal data" step | Mask, don't block: the question usually still makes sense | Block the message; mask in the gateway (would also mask company emails in documents) |
| PERSON and LOCATION are not masked; `acme.example` emails are allowed | Atlas answers questions about colleagues by name and office | Mask names (breaks the org chart questions) |
| `min_score` 0.4, not 0.5 (measured on `evals/guardrails/pii.yaml`): 0.5 caught 6/10, 0.4 caught 9/10 with no order numbers, ticket ids or amounts masked | Presidio scores a bare phone number ~0.4; only context words ("phone", "call") lift it above 0.5 | 0.5 with custom context words |
| New dependencies: `presidio-analyzer`/`-anonymizer` 2.2.366, `en-core-web-sm` 3.8.0 (from GitHub releases); spaCy moved numpy 2.5.4 → 2.4.6 | Approved 2026-11-08 | — |
| `evals/guardrails_run.py`: injection (labelled passages), corpus (what was quarantined), attacks (poisoned-document questions, unprotected vs protected), PII | Every guardrail gets a number, including its false alarms | — |

**Verified live (2026-11-15, after the image rebuild; `UV_HTTP_TIMEOUT=300` added to the Dockerfile after two builds died on a slow network):** the poisoned VPN document re-ingested with its two attack chunks quarantined (provisionally, by heuristics, since no classifier could run) and its two clean chunks kept; a search for "VPN error 691 faster help password" returned neither attack chunk; a chat message "My phone +31 6 1234 5678 …" was saved as "My phone <PHONE_NUMBER> …" with a "Masked personal data" step. **Measured so far:** PII 9/10 caught, 0 ordinary numbers masked. Heuristics 7/10 attacks, 7/10 false alarms. **Not yet measured** (every model was unavailable on 2026-11-13: Claude has no credit, the Ollama Cloud free quota is used up, no local Ollama): the classifier's precision/recall, the corpus scan, and the attack success rate with and without the guardrails.

## 2026-11-16 · Phase 7 checkpoint C: login, permissions, rate limits

| Decision | Why | Alternatives |
| --- | --- | --- |
| **Backend session cookie instead of Auth.js** (chosen 2026-11-16): FastAPI checks the password and sets an httpOnly, SameSite=Lax cookie holding a signed JWT (PyJWT 2.15.1, HS256, `AUTH_SECRET`); Next.js `proxy.ts` only redirects visitors without the cookie to /login | The browser talks to FastAPI directly (chat stream, uploads, images, voice), so FastAPI must own the session; Auth.js would add a second session in Next.js, plus a token for FastAPI, and `<img>` tags can't send a bearer header. Auth.js's strengths (OAuth, SSO, magic links) aren't used by demo passwords | Auth.js Credentials provider (PLAN.md's original choice); server-side sessions in Redis (revocable, one lookup per request) |
| Passwords hashed with stdlib `hashlib.scrypt` (n=2^14, r=8, salt per user), compared with `hmac.compare_digest`; unknown emails are checked against a dummy hash; one error message for both | Slow, memory-hard hashing makes leaked hashes expensive to crack; constant-time paths don't reveal which emails exist | bcrypt/argon2 libraries (new dependency) |
| Every router except /api/auth requires a logged-in user, set once in main.py (`include_router(..., dependencies=[Depends(get_current_user)])`) | A new route can't be added unprotected by forgetting a parameter | A dependency on each route |
| Conversations, messages, images and long-term memories belong to a user (`user_id`, migration 0012). Someone else's conversation id gets the same 404 as a missing one | Per-user data; ids can't be probed | 403 (confirms the id exists) |
| **Permission-aware retrieval** by a request-scoped context variable (`core/access.py`) that the retrieval SQL always reads: the chat, the agent's search_docs, the Knowledge page and the MCP server all filter without passing the user through. The default when nothing is set is `public` only; scripts that need everything use `all_access()` | One filter in one place can't be forgotten on one path; safe by default | Pass the user through every service and tool (interface changes, easy to miss one) |
| Documents get access tags from front matter (`access: [hr]`); the Knowledge page lists, opens and maps only readable documents; the graph build skips restricted documents | A restricted title is information too; graph search can't check who's asking | Show titles, hide contents |
| Two restricted Acme documents: `hr/salary-bands.md` (hr), `finance/budget-2027.md` (finance); demo users Sam (public), Grace (public, hr), Elena (public, finance) in `config/auth.yaml`, created by `python -m scripts.seed_users` with `DEMO_PASSWORD` from .env | Demonstrates and measures the permission filter | — |
| Per-user rate limits in Redis (fixed windows: 10/minute, 200/day; `redis` 7.0.1): chat, approvals and voice return 429 with `Retry-After`; if Redis is down, requests are allowed | INCR is atomic and shared by every backend replica; limits protect cost, and a cache outage shouldn't take the app down | Token bucket / sliding window (smoother, more bookkeeping); in-process counters (per replica) |
| Frontend: pages moved into the `app/(main)` route group, which holds the sidebar; `/login` is outside it. Server Components forward the cookie (`lib/server-session.ts`), browser fetches send `credentials: "include"`; a 401 goes to /login?next=… (same-site paths only) | The login page needs no sidebar, and the alternatives (`usePathname`/`useSelectedLayoutSegment` in the root layout) block prerendering under Next 16 Cache Components | A full-screen overlay on /login (the sidebar would still fetch and 401) |

**Verified:** permissions eval (`evals.guardrails_run --part permissions`, retrieval only, hybrid + graph): 5 questions x 3 users, **0 leaks, 0 misses**. Live API: Sam logs in and sees his 29 earlier conversations and 4 memories, 52 documents, and gets 404 for the salary document; Grace sees 53 documents including it; no cookie or a wrong password gets 401. Browser (throwaway test user, deleted afterwards): /knowledge redirects to /login?next=/knowledge, a wrong password shows the error, login returns to /knowledge, page JavaScript can't read the cookie, the HR user sees the salary document, logout goes back to /login, and a server-rendered /chat/<id> page loads with the forwarded cookie. After moving pages into `(main)`, the dev server's Turbopack cache (the container's anonymous `.next` volume) caused a reload loop on every page; `docker compose up -d -V frontend` fixed it. A route-group move needs that. 179 backend tests.

### To measure once a model is available (deferred 2026-11-16, building without credits)

- Re-ingest with the classifier (`ingestion.run`): the poisoned VPN chunks are quarantined by heuristics only (provisional, rescanned automatically); the one upload hasn't been scanned yet.
- `evals.guardrails_run --part injection`: classifier precision/recall vs heuristics (7/10, 7/10 false alarms).
- `evals.guardrails_run --part attacks`: attack success rate unprotected vs protected (and `--prompt v5` vs v6).
- Phase 7B: semantic cache threshold and cheap/strong routing, built with defaults; tune them on the golden set.
- A full `evals.run` and `evals.agent_run` after Phase 7, for the walkthrough.

## 2026-11-17 · Published on GitHub; first CI run fixed

| Decision | Why | Alternatives |
| --- | --- | --- |
| Frontend type check runs `next typegen` first (`npm run typecheck`) | `PageProps`/`LayoutProps` are generated into `.next/`; a fresh checkout has none, so `tsc` failed in CI while passing locally | Commit generated types (stale, noisy diffs); run a full `next build` in CI (slower) |
| CI ingests with `ingestion.run --text-only` and gates retrieval with `--exclude-tag multimodal` | The scanned PDF and the chart image need the vision model and CI has no model keys; reproduced locally, both failed and the gate fell to 84% because their 5 questions had no source | A model key as a CI secret (costs money per push, credits not available); commit the vision transcripts; let ingestion failures pass (hides real failures) |
| Skipped documents still count as "seen" | Otherwise a `--text-only` run against a real database would delete the scan and image as "removed" | Filter in the source (would prune them) |

**Measured** (CI reproduction, fresh database, no keys, no Neo4j): hit rate 93%, MRR 0.822, so the 0.93 / 0.80 gates pass with no margin. Phase 3 measured 96% / 0.847 on 46 questions; the misses now are `gitlab-ticker-symbol`, `acme-2fa-sms`, `acme-overtime-comp`. Worth a look before the next retrieval change: a single new miss fails CI.

## 2026-11-18 · Back on Claude; Phase 7B checkpoint A: cost ledger and budget cap

| Decision | Why | Alternatives |
| --- | --- | --- |
| Defaults back to Claude (chat + vision: Sonnet 5.5, cheap: Haiku 5.5) | $5 of Anthropic credit added; Ollama Cloud's free quota is used up | Ollama Cloud subscription; local Ollama (free, but a 3B model is unreliable for tools) |
| Sonnet's server-side refusal fallback removed | LiteLLM forwards `extra_body` as a literal field and Anthropic rejects every request ("extra_body: Extra inputs are not permitted") | Patch LiteLLM; pass the field another way (revisit when LiteLLM supports it) |
| Our own `pricing` per model in models.yaml, used before LiteLLM's price map | LiteLLM's bundled map priced Haiku 5.5 at $0, so its spend was invisible. Prices from platform.claude.com: Sonnet $2/$10, Haiku $0.10/$0.50 per million tokens | Upgrade LiteLLM (new dependency version, may still lag) |
| `llm_usage` ledger: one row per model call, written by the gateway (model, purpose = call name, source, user, tokens, cost) | `messages` only had the final answer's cost; routing, rewriting, memory, agent steps, evals and ingestion were uncounted | Read costs back from Langfuse (another service in the loop for the budget check) |
| User and source via a context variable (like the reader's access tags), set by the login dependency and by `begin_script()` in eval/ingestion scripts | No `user_id` threaded through every function; background tasks inherit it | Pass user_id explicitly to every gateway call |
| Daily budget (`budget.daily_usd: 2.00`, UTC day, everyone) and per-run `--budget` on evals; both checked BEFORE a call, new error kind `budget` | Stops a runaway loop or eval from draining the $5; a cost is only known after the call, so a cap can be overshot by one call | Hard-stop mid-stream; per-user budgets (later, with real users) |
| A ledger failure never blocks a call | The cap is a safety net; an answer must not fail because one row couldn't be written | Fail closed (safer for money, worse for users) |
| Per-user spend is visible to every logged-in user on Analytics | Demo app with three fictional users; there are no admin roles yet | Admin-only section (needs roles) |

## 2026-11-18 · Phase 7B checkpoint B: semantic cache

| Decision | Why | Alternatives |
| --- | --- | --- |
| Cache table in pgvector (`semantic_cache`), not Redis | Our Redis image has no vector search; pgvector is already there (principle 5: one database) | Redis Stack (new image); exact-match cache in Redis (people rarely repeat the exact words) |
| Key the cache on the rewritten question's embedding, checked before retrieval | Follow-ups become standalone first, so they can match too; a hit skips retrieval and the answer call | Raw question (follow-ups never match); check after retrieval (slower hits) |
| `scope_key` = hash of access tags, model, prompt version, recalled facts and a knowledge-base stamp (document count + latest update) | An answer is only reused where everything that shaped it matches: an HR answer never reaches non-HR readers, a personal answer never reaches another user, and any ingest/upload/delete starts a fresh cache with no cleanup hooks | Per-user cache (safe but no sharing); TTL only (stale after document changes) |
| **Changed from the approved plan:** recalled facts go INTO the key instead of "skip the cache when memory is used" | Recall returns a user's top 5 facts for every question, so skipping would mean no hits for anyone with memories. Same safety: reuse only with identical facts | Skip on memory (cache useless for real users) |
| Not cached: image questions, "retry", agent actions, answers that were cut off, errored or flagged by the output check | The image is part of the question; retry asks for a new answer; actions must never be replayed | — |
| **Threshold 0.98, not the planned 0.90** (measured with `evals.cache_run`, free: 20 paraphrase pairs, 20 look-alikes) | At 0.90: 60% hits but 2 wrong answers; 0.92: 1 wrong; 0.98: 10% hits, 0 wrong. The embedding model ignores word order ("Who does the IT Manager report to?" vs "Who reports to the IT Manager?" = 0.974) and "vacation days for new employees" vs "after five years" = 0.910 | Verify a candidate hit with the cheap model ("same answer?", ~$0.0001 vs ~$0.005 for an answer) to allow ~0.85 safely: proposed as a follow-up, needs a small paid measurement |
| Evals never use the cache (`make_chat_service(cache=None)`) | An eval must measure the model's answer, not a saved one | — |

**Measured:** threshold table above. **Not yet measured:** hit rate on real traffic (the dashboard now shows hits and dollars saved).

## 2026-11-18 · Phase 7B checkpoint C: model routing ("Auto")

| Decision | Why | Alternatives |
| --- | --- | --- |
| "Auto" in the model menu (preselected); `routing: {simple: claude-haiku, complex: claude-sonnet}` in models.yaml | Use the cheapest model that is good enough per question, as a config change | Always Sonnet (simple, ~2.5x the answer cost); a trained router model |
| The existing intent classifier also outputs `complexity` (prompt `classify_intent` v2) | It already runs on every message for agent routing: no extra call, no extra latency | A separate routing call; heuristics (question length, keywords) |
| Agent turns, image questions and failed classifications always use the complex model; a named model is never rerouted | A wrong "simple" costs answer quality, a wrong "complex" only money; tool calls must be exact | Route agent steps too |
| API fallback when a request names no model stays `defaults.chat`; only the UI preselects Auto | Scripts, the MCP server and the graph build need a real model id | Default everything to Auto |

**Measured** (golden set v2, 55 questions, judge Haiku 5.5, $0.49 for all of today's measurements):

| | Sonnet on every question | Auto |
| --- | --- | --- |
| Answered by | Sonnet 55 | Haiku 34, Sonnet 21 |
| Answer cost | $0.295 | **$0.116 (-61%)**; about $0.127 with the classifier calls (which the chat makes anyway) |
| Avg latency | 2.1 s | **1.6 s** |
| Correctness (judge) | 82% | 83% |
| Faithfulness (judge) | 97% | 96% |
| Cited the right source | 96% | 92% (Haiku left the citation off 2 simple GitLab questions: async, DRI) |
| Hit rate / MRR | 96% / 0.865 | same (retrieval doesn't depend on the answer model) |

Classifier check before the runs: agent routing still 12/12 with prompt v2; 34 of 55 golden questions labelled simple. Per-question differences go both ways (12 questions changed by half a point or more), so with 55 questions and a Haiku judge a 1-point difference is noise. Weakest categories for both: keyword (50-58%) and relational (69%), a retrieval/graph issue, not a model one.

## 2026-11-18 · Phase 7D: deploy-ready (no public deploy)

| Decision | Why | Alternatives |
| --- | --- | --- |
| Multi-stage Dockerfiles with `dev` and `prod` targets; `docker-compose.prod.yml` layered on the dev file | One source of truth for services; prod only overrides what differs | A separate full prod compose file (drifts from dev) |
| Next.js `output: "standalone"`, served by `node server.js` as a non-root user | 300 MB image with only traced files; login page 0.03 s first load vs 1.0 s in dev mode | `next start` with all node_modules (bigger image) |
| Backend prod image runs as non-root `atlas`, code read-only, `--proxy-headers`, one worker | Least privilege; behind an HTTPS proxy the app must trust X-Forwarded-*; each worker loads the embedding model, so scale with containers | Several uvicorn workers (memory x N) |
| Migrations in a one-off `migrate` container that the backend waits for (`service_completed_successfully`) | Several backends running `alembic upgrade` on start could race | Keep migrate-on-start (fine for one container only) |
| `AUTH_SECURE_COOKIE` env var overrides config/auth.yaml; prod defaults it to true | The deployment, not the repo, knows whether it has HTTPS | Separate auth.prod.yaml |
| Prod publishes only 3000, 8000 and 3001 (`ports: !reset []` elsewhere); separate prod volumes for model cache and uploads | Databases must not face the internet; dev volumes are root-owned | Firewall-only protection |
| CI adds `npm run build` and builds both prod images with plain `docker build` | A production-only failure (prerendering, Dockerfile) fails the PR, not the deploy; no extra third-party action to pin | docker/build-push-action (another dependency) |
| One VM + Caddy documented as the deployment path (docs/deploy.md), frontend and API on one site | 11 services; one Compose stack is simpler than four managed services; `SameSite=Lax` cookies need one registrable domain | Vercel + Render + Neo4j Aura + Langfuse Cloud |

**Verified:** `next build` passes (all pages; dynamic ones as partial prerender). The prod frontend image ran beside the dev stack: /login in 0.03 s first, 0.005 s after (dev: 1.0 s / 0.25 s), as user `atlas`, protected pages redirect to login. The prod backend image imports the app as `atlas`, can write uploads, can't modify its code, and `AUTH_SECURE_COOKIE=true` turns secure cookies on. The merged prod Compose config validates. **Not verified:** the whole prod stack started end to end (it shares ports with the running dev stack), and HTTPS on a real domain.

**Found:** `npm audit` flags next 16.4.2 (moderate, GHSA-mfr8-8qww-v76h and GHSA-vc7v-qv4w-wrv8: cache leaks through `use cache` / `unstable_cache`, which Atlas doesn't use); fixed in 16.4.6. Upgrade pending approval.
