"""POST /api/chat: send a message, receive the answer as a Server-Sent Events stream.

Response body (text/event-stream), one event per `data:` line, for example:
    data: {"type":"token","text":"Atlas was"}
    data: {"type":"token","text":" a Titan"}
    data: {"type":"done","message_id":"...","usage":{...},"prompt_ref":"chat_system@v1"}
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import CatalogDep, ChatServiceDep
from core.events import to_sse
from services.chat_service import ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",  # never cache a live stream
    "X-Accel-Buffering": "no",  # tell proxies like nginx not to buffer (they'd delay tokens)
}


@router.post("/chat", response_class=StreamingResponse)
async def chat(request: ChatRequest, chat_service: ChatServiceDep, catalog: CatalogDep):
    # Validate what we can BEFORE streaming starts: once the 200 + first bytes are sent,
    # the HTTP status can't change, so later problems must travel as `error` events instead.
    model_id = request.model_id or catalog.defaults.chat
    if catalog.get(model_id) is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{model_id}'")

    async def sse() -> AsyncIterator[str]:
        async for event in chat_service.stream_reply(request, model_id):
            yield to_sse(event)

    return StreamingResponse(sse(), media_type="text/event-stream", headers=SSE_HEADERS)
