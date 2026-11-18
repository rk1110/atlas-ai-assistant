"""POST /api/chat: send a message, receive the answer as a Server-Sent Events stream.

Response body (text/event-stream), one event per `data:` line, for example:
    data: {"type":"token","text":"Atlas was"}
    data: {"type":"token","text":" a Titan"}
    data: {"type":"done","message_id":"...","usage":{...},"prompt_ref":"chat_system@v1"}
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import CatalogDep, ChatServiceDep, RateLimitedUserDep
from core.events import AgentStepEvent, to_sse
from guardrails.pii import PiiMasker, get_pii_masker
from services.chat_service import ApprovalDecision, ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",  # never cache a live stream
    "X-Accel-Buffering": "no",  # tell proxies like nginx not to buffer (they'd delay tokens)
}


PiiMaskerDep = Annotated[PiiMasker, Depends(get_pii_masker)]


@router.post("/chat", response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    chat_service: ChatServiceDep,
    catalog: CatalogDep,
    pii: PiiMaskerDep,
    user: RateLimitedUserDep,
):
    # Validate what we can BEFORE streaming starts: once the 200 + first bytes are sent,
    # the HTTP status can't change, so later problems must travel as `error` events instead.
    model_id = request.model_id or catalog.defaults.chat
    if not catalog.is_selectable(model_id):
        raise HTTPException(status_code=400, detail=f"Unknown model '{model_id}'")
    if not await chat_service.owns_conversation(request.conversation_id, user.id):
        # 404, not 403: don't even confirm that someone else's conversation exists.
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:  # Phase 6: a bad image is a clean 400 now, not an error mid-stream
        images = chat_service.decode_images(request)
    except ValueError as exc:  # ImageError is a ValueError
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Phase 7: mask personal data first, so the database, memory, traces and every model only
    # ever see the masked text. Both paths (RAG and agent) start from this request.
    masked = await pii.mask(request.message)
    if masked.found:
        request = request.model_copy(update={"message": masked.text})

    async def sse() -> AsyncIterator[str]:
        if masked.found:
            yield to_sse(
                AgentStepEvent(
                    step_id="mask_pii",
                    agent="guardrails",
                    status="completed",
                    title="Masked personal data",
                    detail=f"{masked.summary()}: replaced before Atlas saved or sent your message.",
                )
            )
        async for event in chat_service.stream_reply(request, model_id, images, user.id):
            yield to_sse(event)

    return StreamingResponse(sse(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/chat/approval", response_class=StreamingResponse)
async def approval(
    decision: ApprovalDecision,
    chat_service: ChatServiceDep,
    catalog: CatalogDep,
    user: RateLimitedUserDep,
):
    """The human's answer to an approval card. Resumes the paused agent run and streams the
    rest of the turn (the approved action, then the answer) exactly like POST /api/chat.

    404 before streaming if no run in this conversation is waiting for this approval: e.g.
    it was already answered, or the id belongs to another conversation.
    """
    model_id = decision.model_id or catalog.defaults.chat
    if not catalog.is_selectable(model_id):
        raise HTTPException(status_code=400, detail=f"Unknown model '{model_id}'")
    owner = await chat_service.owns_conversation(decision.conversation_id, user.id)
    if not owner or not await chat_service.check_approval(decision):
        raise HTTPException(status_code=404, detail="No action is waiting for this approval")

    async def sse() -> AsyncIterator[str]:
        async for event in chat_service.resume_approval(decision, model_id, user.id):
            yield to_sse(event)

    return StreamingResponse(sse(), media_type="text/event-stream", headers=SSE_HEADERS)
