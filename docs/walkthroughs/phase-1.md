# Phase 1 walkthrough: Foundation

Listen to it: `say -f docs/walkthroughs/phase-1.md` (or `-o ~/phase-1.aiff` to save audio).
See it: the Atlas Map at https://claude.ai/artifact/8tN6jDQixPMf2eeq56qFgN plays the same request flow step by step.

## What Phase 1 built

Phase 1 built the skeleton of the final system. You can open the web app, chat with a model, and watch the answer stream in word by word. You can switch models. Every model call is traced in Langfuse. A golden set of questions measures the system, and a test suite protects it.

Nothing here answers from company documents yet. That is Phase 2. Phase 1 exists so that Phase 2 only has to add retrieval, not build an app around it.

There are three big pieces. The backend is FastAPI in Python. It holds all the AI logic. The frontend is Next.js in TypeScript. It only draws the interface and reads the stream. The data layer is Postgres for app data, and Langfuse for traces. Docker Compose starts all of it with one command.

## The journey of one message

This is the most important section. It follows one message from the moment you press Enter until the last word appears.

**Step 1. You press Enter.** The composer component catches the key press. Shift plus Enter would add a new line instead. If this is a new chat, the page now creates a conversation id, a random UUID. It does this on the first send, not when the page renders. Next.js pre-builds pages, and a random value created during rendering would be frozen into the pre-built page.

**Step 2. The browser sends the request.** The hook `use-chat-stream.ts` calls `fetch` with a POST to `/api/chat`. The body holds the conversation id, your message, and the chosen model id. It also creates an AbortController. That is what the Stop button uses later.

**Step 3. The browser is allowed to talk to the backend.** The page lives on port 3000 and the backend on port 8000. Browsers block that by default. The backend's CORS settings allow exactly one origin: the Atlas frontend.

**Step 4. FastAPI checks the request.** Pydantic validates the body. An empty message gets a 422 error. An unknown model id gets a 400 error. These checks happen before streaming starts, because once the stream starts, the HTTP status is already 200 and can't change.

**Step 5. The chat service takes over.** The route is thin. It hands the work to `ChatService.stream_reply`, which is plain Python with no HTTP in it. That is why the eval runner can reuse the same code.

**Step 6. A trace begins.** The service starts a Langfuse trace called `chat_turn`. Its session id is the conversation id, so Langfuse can group a whole conversation.

**Step 7. Your question is saved first.** The service opens its own database session. It creates the conversation if it is new, saves your message, and commits. This happens before any model call. If the model fails, your question is not lost.

**Step 8. History is loaded.** The service loads the last 20 messages of this conversation. Answers that were cut off by an error are skipped. Models remember nothing between calls, so this history is the model's short-term memory. It is sent again on every turn.

**Step 9. The system prompt is rendered.** The prompt registry fills in `chat_system` version 1 with the assistant's name and today's date. The result is placed in front of the history. Its name and version, `chat_system@v1`, travel with the request from here on.

**Step 10. The model is resolved.** The gateway looks up the model id in `config/models.yaml`. For example, `gpt-oss-cloud` becomes the LiteLLM string `ollama_chat/gpt-oss:120b`, the Ollama Cloud address, your API key, and temperature 0.7.

**Step 11. The gateway calls the model.** `core/llm.py` is the only file that talks to a model. It opens a Langfuse generation inside the trace, then calls LiteLLM with streaming turned on. LiteLLM translates the call into the provider's own format.

**Step 12. The model generates.** The model reads about 200 input tokens: the system prompt, the history, and your question. After roughly one second, the first token comes back. GPT-OSS is a reasoning model, so it sometimes thinks for a few seconds before its first visible word.

**Step 13. Chunks become events.** Each chunk from the provider becomes a `TextDelta` inside the gateway. The chat service turns each delta into a `token` event. The function `to_sse` writes it as one line starting with `data:`, followed by a blank line. That is the Server-Sent Events format.

**Step 14. The browser reads the stream.** Network packets don't line up with events. One read can hold half an event, or three. The hook keeps a text buffer and cuts out a complete event at every blank line. It parses the JSON and checks the `type` field. For a `token` event, it appends the text to the answer bubble. That is the typing effect you see.

**Step 15. The answer is saved.** When the model finishes, the gateway reports tokens, cost, latency, and time to first token. The service saves the answer with all of that, plus the prompt version and the trace id. It closes the Langfuse trace.

**Step 16. The stream ends with done.** The last event is always `done`, even after an error. It carries the saved message id, the usage numbers, the prompt version, and a link to the trace. The page stops the spinner and shows the small print under the answer, including "View trace".

**Step 17. The sidebar refreshes.** The page fires a small browser event. The conversation list hears it and reloads. A new chat also gets its own address, `/chat/` followed by its id, so you can bookmark it or reload it.

**If something fails.** A model error becomes an `error` event with a short, safe message, followed by `done`. The raw provider error only goes to the server log. If the error can help to retry, such as a rate limit, the UI shows "Try again".

**If you press Stop.** The browser aborts the request. The server sees a cancelled task. The service saves the partial answer, marked as cancelled, inside a shielded block. Without the shield, the save itself would be cancelled too.

## What each file does

A reference for reading the code. When listening, skip to the next section.

### Infrastructure

| File | Role |
| --- | --- |
| `docker-compose.yml` | The 8 services, health checks, start order, ports, volumes |
| `infra/postgres/init.sql` | Creates the `langfuse` and `atlas_test` databases on a fresh volume |
| `backend/Dockerfile`, `frontend/Dockerfile` | Images, with dependencies installed in a cached layer |
| `.env.example` | Every setting, with placeholders and the password rules |

### Backend core (`backend/core/`)

| File | Role |
| --- | --- |
| `config.py` | Typed settings from env / `.env`; secrets are masked |
| `model_catalog.py` + `config/models.yaml` | Which models exist, how to call them, whether each is usable now |
| `llm.py` | The gateway: streaming chat and structured output, errors, cost, tracing |
| `tracing.py` | The Langfuse wrapper. It does nothing if Langfuse is off, and never breaks the app |
| `prompts.py` + `prompts/*.yaml` | Versioned prompts with validated variables |
| `events.py` | The 7 stream event types and the SSE encoder |
| `db.py` | Async engine, sessions, naming convention |
| `interfaces/` | `DataSource`, `Retriever`, `Tool`, `Agent`: the extension points for later phases |

### Backend features

| File | Role |
| --- | --- |
| `api/chat.py` + `services/chat_service.py` | POST /api/chat: one chat turn, streamed |
| `api/conversations.py` | List, open, delete conversations |
| `api/models.py` | The model list for the dropdown |
| `api/classify.py` + `services/intent.py` | Structured output: intent classification |
| `models/` + `migrations/versions/` | Tables, and the migrations that create them (0001 chat, 0002 evals) |
| `evals/` | Golden set, schema, runner |
| `tests/` | 39 tests with a fake model |

### Frontend

| File | Role |
| --- | --- |
| `app/layout.tsx` | Theme, sidebar, and toasts, shared by every page |
| `app/page.tsx`, `app/chat/[id]/page.tsx` | New chat; an existing conversation, rendered on the server |
| `app/knowledge`, `graph`, `analytics`, `settings` | The other pages, ready for their phases |
| `components/app-sidebar.tsx`, `nav-main.tsx`, `conversation-list.tsx` | Navigation and history |
| `components/chat/*` | The chat page, split into small components |
| `lib/use-chat-stream.ts` | Sends the message and reads the stream |
| `lib/events.ts` | The TypeScript mirror of the event contract |

## Why it is built this way

The decision log, `docs/decisions.md`, has every choice with its alternatives. These are the ones that matter most.

**One gateway for all model calls.** Every call goes through `core/llm.py`. Switching from Claude to Ollama took one line of YAML, with no code. Tracing was added in one place, and every call got it. The alternative is calling provider SDKs wherever they are needed. That spreads provider details across the codebase, and every new cross-cutting feature has to be added many times.

**A fixed event contract from day one.** All 7 event types exist now, though Phase 1 sends only 3. Later phases only start sending events that the frontend already understands. The alternative, adding events as needed, means changing both sides every phase. Drift tests keep the Python and TypeScript copies identical.

**Server-Sent Events, read with fetch.** SSE is plain HTTP and one-way, which is exactly the chat pattern. WebSockets would add a second protocol for two-way talk we don't need. The browser's EventSource can't send a POST body, so we read the stream ourselves.

**Save the question before calling the model.** Failures are normal with remote models. Saving first means a failure never loses the user's question.

**Structured output, native or by prompt.** Some providers enforce a JSON schema while generating. Ollama Cloud ignores schemas, which we discovered by testing. So each model declares which mode it uses. In prompt mode, the schema goes into the prompt, and the reply is validated and retried once. The caller always gets a validated object.

**Tracing never breaks the app.** If Langfuse is down, chat keeps working and traces are lost. Observability matters, but it is not worth an outage.

**Migrations, not create-all.** Every schema change is a reviewed script. Tests build their database the same way production does.

**Tests with a fake model.** 39 tests run in about one second for free. They check exactly what the model was sent, such as whether the history was included.

## What to look at next

Open a trace in Langfuse and match it against the journey above. Run the evals, then open `backend/evals/results/` and the Langfuse session for that run. Read `core/llm.py` from top to bottom. It is the heart of the backend.

## Your exercises

Write these yourself. Ask for a review when done, or for a hint if you're stuck.

**Exercise 1. Grow the golden set, then compare two models.**
Add 15 questions to `backend/evals/golden_set.yaml`, for 20 in total. Mix GitLab handbook questions with Acme questions, and give every Acme answer a specific, checkable fact. Then run the evals twice: once with `gpt-oss-cloud`, once with `gpt-oss-20b-cloud`. Record both runs' average latency, output tokens and error count in `docs/decisions.md`, with one sentence on which model you'd pick for chat, and why.
Done when: `uv run pytest tests/test_evals.py` passes, and the decision log has your two numbers.

**Exercise 2. Ship a prompt v2 and measure it.**
Add version `v2` to `prompts/chat_system.yaml`. Make one deliberate change, for example: answers stay under 120 words, and end with one suggested follow-up question. Switch `active` to `v2`, restart the backend, and run the evals. Compare against your v1 run: did output tokens and latency change? Find a v2 answer in Langfuse by its version.
Done when: v1 is unchanged in the file, v2 is active, and you can state the difference in numbers.

**Exercise 3. Fix the duplicate question on "Try again".**
Right now, Try again sends the last question again, so it appears twice in the conversation and in the database. Make retry produce a new answer without saving a second copy of the question. Decide where the fix belongs: frontend, backend, or both. Write at least one backend test that fails before your fix and passes after it.
Done when: retrying shows the question once, and `uv run pytest` passes.
