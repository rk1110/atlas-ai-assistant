# .github/workflows/

`ci.yml` runs on every pull request and every push to `main`:

| Job | What | Fails when |
| --- | --- | --- |
| `backend` | ruff + pytest on Postgres/pgvector | lint or a test fails |
| `frontend` | eslint + `tsc --noEmit` | lint or a type error |
| `retrieval-evals` | ingest `data/` with the real embedding model, golden set retrieval-only | hit rate < 93% or MRR < 0.80 |

Full evals (answers + LLM judge) need provider API keys and cost money, so they run on demand
with `docker compose exec backend python -m evals.run`.
