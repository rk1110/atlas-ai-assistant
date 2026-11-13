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
from services.chat_service import ApprovalDecision, ChatRequest

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
    try:  # Phase 6: a bad image is a clean 400 now, not an error mid-stream
        images = chat_service.decode_images(request)
    except ValueError as exc:  # ImageError is a ValueError
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def sse() -> AsyncIterator[str]:
        async for event in chat_service.stream_reply(request, model_id, images):
            yield to_sse(event)

    return StreamingResponse(sse(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/chat/approval", response_class=StreamingResponse)
async def approval(decision: ApprovalDecision, chat_service: ChatServiceDep, catalog: CatalogDep):
    """The human's answer to an approval card. Resumes the paused agent run and streams the
    rest of the turn (the approved action, then the answer) exactly like POST /api/chat.

    404 before streaming if no run in this conversation is waiting for this approval: e.g.
    it was already answered, or the id belongs to another conversation.
    """
    model_id = decision.model_id or catalog.defaults.chat
    if catalog.get(model_id) is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{model_id}'")
    if not await chat_service.check_approval(decision):
        raise HTTPException(status_code=404, detail="No action is waiting for this approval")

    async def sse() -> AsyncIterator[str]:
        async for event in chat_service.resume_approval(decision, model_id):
            yield to_sse(event)

    return StreamingResponse(sse(), media_type="text/event-stream", headers=SSE_HEADERS)
