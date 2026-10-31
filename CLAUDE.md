# CLAUDE.md — Atlas: AI Knowledge Assistant + Action Agent

This file is read at the start of every Claude Code session. Follow it unless I explicitly say otherwise in the session.

## What this project is

Atlas is a web app where employees chat with company knowledge and a team of AI agents takes actions for them (e.g. answering a policy question with citations, then opening a Jira ticket after human approval). Every agent step is shown live in the UI.

**The primary goal is for me (the developer) to LEARN modern AI engineering.** Shipping features is secondary. Optimise for my understanding, not just for working code.

- Full plan and source of truth: `docs/PLAN.md`
- Data: public GitLab handbook + a fictional company corpus ("Acme Corp") in `data/`. No internal company data unless I explicitly add a new `DataSource` for it.

## Timeline override

`docs/PLAN.md` mentions ~22 weeks. That is replaced by: **one phase per week, about 8 weeks total.** You (Claude Code) write most of the code; I learn through the loop below. No feature or learning topic from the plan is dropped.

## How we work: the learning loop (every phase)

1. **Plan first.** Before writing code for a phase or a big feature, show me a short plan: files to create/change, key design choices, and which AI concepts this teaches. Wait for my OK.
2. **Build in small steps.** One logical step at a time, each runnable. Suggest a git commit message after each working step.
3. **Explain as you go.** When you introduce a new AI concept (embeddings, reranking, agent loop, MCP, etc.), add a 2–3 sentence plain-English explanation in your reply.
4. **Walkthrough doc.** At the end of each phase, write `docs/walkthroughs/phase-N.md`: what each new file does, how one request flows through the system step by step, why each design choice was made, and what alternatives exist.
5. **Concept quiz.** When I say "quiz me", ask 8–10 questions about this phase, one at a time. Wait for my answer, then give honest feedback. Do not reveal answers before I try.
6. **My exercises.** Give me 2–3 small changes to implement myself (e.g. add a tool, change the chunking strategy and compare eval scores). **Do not write that code for me.** Review my code when I ask, and give hints rather than full solutions unless I'm stuck and ask for the answer.
7. **Break and fix.** When I say "break it", introduce one realistic bug on a separate git branch without telling me where it is, describe only the symptom, and let me debug it. Give hints only if asked.
8. **Decision log.** Append important choices to `docs/decisions.md` (date, decision, why, alternatives considered).

## Locked-in architecture principles (never violate without asking me)

1. Separate frontend (Next.js) and backend (FastAPI) from day one. Later phases add modules, never restructure.
2. All LLM calls go through the LiteLLM gateway in `backend/core/`. No direct provider SDK calls elsewhere.
3. Interfaces before implementations: `DataSource`, `Retriever`, `Tool`, `Agent`, `StreamEvent`. New sources/tools are new files implementing these.
4. The backend streams typed events (`token`, `citation`, `agent_step`, `tool_call`, `approval_request`, `error`, `done`) over SSE. Frontend types in `frontend/lib/events.ts` must mirror backend types exactly.
5. One database: PostgreSQL + pgvector for app data, chat history, memory, eval results and vectors.
6. Observability (Langfuse) and evals exist from Phase 1. Every new feature must be traceable and, where possible, covered by an eval.
7. Everything runs with `docker compose up`.
8. Prompts, model names, chunk sizes and feature flags live in config / `prompts/` (versioned YAML), never hard-coded.

## Tech stack (do not add alternatives without asking)

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui; Vercel AI SDK for chat UI; Framer Motion, React Flow, Recharts.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy + Alembic, uv (or pip) for deps.
- **AI:** LiteLLM, LangGraph, sentence-transformers (embeddings/reranker), RAGAS, official MCP Python SDK.
- **Infra:** PostgreSQL + pgvector, Redis, Langfuse (self-hosted), Neo4j (Phase 3+), Docker Compose, GitHub Actions.
- **Models:** Claude as the main model, a cheaper model for routing/evals, Ollama for local/offline.

Pin exact versions of all dependencies. Before adding any new library, tell me what it is for and wait for approval.

## Coding conventions

- Python: type hints everywhere, async FastAPI routes, Pydantic models for all inputs/outputs, `ruff` for lint/format, `pytest` for tests.
- TypeScript: strict mode, no `any`, components in `frontend/components/`, one component per file.
- Keep functions small and readable; I need to understand them. Prefer clarity over cleverness.
- Add docstrings explaining **why**, not just what, especially in AI logic (retrieval, prompts, agent graphs).
- Every new backend module gets at least basic tests.

## Safety and secrets

- Secrets only in `.env` (git-ignored). Keep `.env.example` updated with placeholder values.
- Never print, log, or commit API keys.
- Never run destructive commands (dropping databases, `rm -rf`, force-push) without asking me first.
- Any agent tool that writes to external systems (Jira, Slack, email) must go through human approval.

## Common commands (keep this section updated)

```bash
docker compose up -d                       # start the full stack (9 services); `docker compose ps` = health
docker compose logs -f backend             # follow backend logs
docker compose restart backend             # after editing config/models.yaml or prompts/*.yaml
docker compose up -d --build backend       # after changing backend dependencies (pyproject/uv.lock)
docker compose up -d --build -V frontend   # after changing frontend dependencies (-V renews node_modules)

cd backend && uv run pytest                # backend tests (on your Mac; uses the atlas_test DB, fake LLM)
cd backend && uv run ruff check . && uv run ruff format .   # lint + format
docker compose exec backend python -m evals.run             # eval suite (real model calls)
docker compose exec backend python -m evals.run --model gpt-oss-20b-cloud --notes "what changed"
docker compose exec backend python -m evals.run --retrieval-only   # hit rate + MRR only, no model calls (free)
docker compose exec backend python -m evals.run --retrieval-only --retriever all   # compare retrieval strategies
docker compose exec backend python -m evals.run --retriever vector --no-rewrite    # full run with Phase 2 settings
docker compose exec backend python -m evals.run --no-judge  # skip the LLM-as-judge scores
docker compose exec backend python -m scripts.smoke_llm     # one streamed reply per model
docker compose exec backend python -m ingestion.run          # load data/ into the knowledge base (skips unchanged)
docker compose exec backend python -m ingestion.run --force  # re-embed all (after changing config/rag.yaml)
docker compose exec backend python -m graph.build            # extract Acme docs into Neo4j (skips unchanged; --force)
cd backend && uv run python -m scripts.fetch_gitlab_handbook # refresh data/gitlab at the pinned commit

docker compose exec backend alembic revision --autogenerate --rev-id 000N -m "what"  # new migration (review it!)
docker compose exec backend alembic upgrade head            # apply migrations (also runs on backend start)

cd frontend && npm run lint && npx tsc --noEmit             # frontend lint + type check
cd frontend && npm run dev                                  # frontend outside Docker
```

| URL | What |
| --- | --- |
| http://localhost:3000 | Atlas web app (/knowledge, /graph, /analytics) |
| http://localhost:8000/docs | Backend API docs |
| http://localhost:3001 | Langfuse (traces; login from `.env`) |
| http://localhost:7474 | Neo4j browser (user `neo4j`, password `NEO4J_PASSWORD` from `.env`) |

## Phase status (update when a phase is done)

| Phase | Name | Status |
| --- | --- | --- |
| 1 | Foundation (app shell, streaming chat, gateway, tracing, eval scaffold) | Done (2026-10-29; exercise 3 solved by Claude at my request) |
| 2 | Core RAG (ingestion, embeddings, pgvector, citations, Knowledge Base page) | Built (checkpoints A–C, cited correct 90%); walkthrough written; quiz + exercises pending |
| 3 | Advanced RAG + evals (hybrid, reranker, query rewriting, GraphRAG, CI evals) | Built in one shot at my request (2026-10-30); walkthrough written; quiz + exercises pending (Phase 2's too) |
| 4 | Agents + tools (LangGraph agent, tools, approval cards, memory) | Not started |
| 5 | Multi-agent + MCP (4-agent team, Jira/Slack MCP, own MCP server, agent graph UI) | Not started |
| 6 | Multimodal + voice | Not started |
| 7 | Production-ready (guardrails, caching, routing, auth, cost dashboard, deploy) | Not started |
| 8 | Fine-tune + launch (Ollama, LoRA, demo video, README) | Not started |

A phase is "Done" only when its "Done when" criteria in `docs/PLAN.md` are met, the walkthrough doc exists, and I've completed the quiz and my exercises.
