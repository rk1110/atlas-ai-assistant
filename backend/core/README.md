# core/

The foundation every other module depends on (built in Phase 1, step 3):

- `config.py` — typed settings read from `.env` (Pydantic Settings)
- `llm.py` — the **only** place that calls LLMs, via LiteLLM
- `prompts.py` — loads versioned YAML prompts from `/prompts`
- `events.py` — typed `StreamEvent` models streamed to the UI
- `db.py` — async SQLAlchemy engine/session
- `interfaces/` — abstract `DataSource`, `Retriever`, `Tool`, `Agent`
