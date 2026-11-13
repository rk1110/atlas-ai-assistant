"""Conversation history for the sidebar: list, open, delete."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import SessionDep, TracerDep
from core.events import AgentLog, CitationEvent
from models import Conversation, Message, MessageImage

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    model_id: str | None
    error_code: str | None  # e.g. "billing", or "cancelled" when the user pressed Stop
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    trace_url: str | None
    citations: list[CitationEvent]  # the chips under an answer, same shape as the live event
    agent: AgentLog | None  # agent answers: steps, tool calls, approval cards (Phase 4)
    images: list["ImageRef"] = []  # user messages with attached images (Phase 6)


class ImageRef(BaseModel):
    """An attached image, fetched separately from GET /api/images/{id} (bytes stay out of JSON)."""

    id: uuid.UUID
    media_type: str
    description: str | None


@router.get("")
async def list_conversations(session: SessionDep, limit: int = 50) -> list[ConversationSummary]:
    """Most recently active first: the sidebar order."""
    rows = await session.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(min(limit, 200))
    )
    return [
        ConversationSummary(id=c.id, title=c.title, updated_at=c.updated_at) for c in rows.all()
    ]


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID, session: SessionDep, tracer: TracerDep
) -> list[MessageOut]:
    if await session.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role != "system")
            .order_by(Message.created_at)
        )
    )
    images: dict[uuid.UUID, list[ImageRef]] = {}
    image_rows = await session.execute(
        select(MessageImage.id, MessageImage.message_id, MessageImage.media_type,
               MessageImage.description)
        .where(MessageImage.message_id.in_([m.id for m in rows]))
        .order_by(MessageImage.ordinal)
    )  # fmt: skip
    for image_id, message_id, media_type, description in image_rows.all():
        images.setdefault(message_id, []).append(
            ImageRef(id=image_id, media_type=media_type, description=description)
        )
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            model_id=m.model_id,
            error_code=m.error_code,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            latency_ms=m.latency_ms,
            trace_url=tracer.trace_url(m.trace_id),
            citations=[CitationEvent.model_validate(c) for c in m.citations or []],
            agent=AgentLog.model_validate(m.agent) if m.agent else None,
            images=images.get(m.id, []),
        )
        for m in rows
    ]


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, session: SessionDep) -> Response:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await session.delete(conversation)  # messages go too (ON DELETE CASCADE)
    await session.commit()
    return Response(status_code=204)
