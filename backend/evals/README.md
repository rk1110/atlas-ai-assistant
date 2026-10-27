# evals/

Measure every change with numbers instead of impressions.

| File | Purpose |
| --- | --- |
| `golden_set.yaml` | Questions with known answers and the documents that contain them (format documented inside) |
| `schema.py` | Pydantic schema: the file is validated before any model call |
| `run.py` | Runner: answers every question with the chat model; saves to Postgres, `results/*.json`, and Langfuse |
| `results/` | JSON reports (git-ignored) |

```bash
docker compose exec backend python -m evals.run                         # all questions, default chat model
docker compose exec backend python -m evals.run --tag acme --limit 2     # a subset
docker compose exec backend python -m evals.run --model gpt-oss-20b-cloud --notes "try 20B"
```

In Langfuse each run is a session named `eval-<run id>`; traces are tagged `eval`.

Roadmap: Phase 1 records answers, latency, tokens and cost. Phase 2 adds retrieval metrics
(hit rate, MRR against `expected_sources`). Phase 3 adds answer scoring (RAGAS, LLM-as-judge)
and runs evals in CI on every pull request.
