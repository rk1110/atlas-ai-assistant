# Atlas — AI Knowledge Assistant + Action Agent

Atlas is a web app where employees chat with company knowledge, and a team of AI agents takes actions
for them (answering a policy question with citations, then opening a Jira ticket after human approval).
Every agent step is shown live in the UI.

> Status: **Phase 1 — Foundation** (in progress). See [`docs/PLAN.md`](docs/PLAN.md) for the full roadmap.

## Architecture at a glance

| Layer | Tech |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn/ui |
| Backend | FastAPI, Pydantic v2, SQLAlchemy + Alembic |
| LLM gateway | LiteLLM (Claude, Ollama, …) |
| Data | PostgreSQL + pgvector, Redis |
| Observability | Langfuse (self-hosted) |

The backend streams typed events (`token`, `citation`, `agent_step`, `tool_call`, `approval_request`,
`error`, `done`) to the frontend over Server-Sent Events.

## Prerequisites

- Docker Desktop (with Docker Compose v2+)
- [uv](https://docs.astral.sh/uv/) for Python (`brew install uv`) — needed to run backend tests/evals locally
- Node.js 20+ — only if you run the frontend outside Docker
- An Anthropic API key (set a monthly spend limit on it)
- Optional: [Ollama](https://ollama.com) on your host for local models (`ollama pull llama3.2`)

## Setup

```bash
git clone <this repo> atlas && cd atlas
cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY and replace every "change-me" / "replace" value
# (generate secrets with: openssl rand -hex 32)

docker compose up -d        # start everything
docker compose ps           # all services should show "healthy"
```

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| Backend API docs | http://localhost:8000/docs |
| Langfuse | http://localhost:3001 |

## Repository layout

```
frontend/   Next.js app            backend/   FastAPI + all AI logic
prompts/    versioned prompt YAML  config/    model list and other non-secret config
data/       knowledge-base docs    infra/     init scripts, deploy configs
docs/       plan, walkthroughs, decision log
```

Each folder has a README describing what lives there and in which phase it gets built.

## Learning docs

- [`docs/PLAN.md`](docs/PLAN.md) — full plan
- [`docs/walkthroughs/`](docs/walkthroughs/) — one walkthrough per phase
- [`docs/decisions.md`](docs/decisions.md) — decision log
