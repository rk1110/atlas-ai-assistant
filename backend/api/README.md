# api/

FastAPI routers. Routes stay thin: validate input (Pydantic), call a service, return/stream the result.
Phase 1: `chat.py` (SSE streaming), `conversations.py`, `models.py`, `classify.py` (structured output demo).
