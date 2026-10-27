"""POST /api/chat end to end (HTTP -> service -> DB) with a fake LLM."""

import json
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from core.db import get_session_factory
from core.llm import LLMError
from models import Message
from tests.conftest import FakeGateway


def sse_events(body: str) -> list[dict]:
    return [json.loads(f[len("data: ") :]) for f in body.split("\n\n") if f.startswith("data: ")]


async def chat(client: AsyncClient, conversation_id: str, message: str, **extra) -> list[dict]:
    response = await client.post(
        "/api/chat", json={"conversation_id": conversation_id, "message": message, **extra}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse_events(response.text)


async def saved_messages(conversation_id: str) -> list[Message]:
    async with get_session_factory()() as session:
        rows = await session.scalars(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
            .order_by(Message.created_at)
        )
        return list(rows)


async def test_streams_tokens_then_done_and_saves_both_messages(client: AsyncClient):
    cid = str(uuid.uuid4())
    events = await chat(client, cid, "Hi there")

    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Hello world"
    done = events[-1]
    assert done["usage"]["input_tokens"] == 10 and done["prompt_ref"] == "chat_system@v1"

    user, assistant = await saved_messages(cid)
    assert (user.role, user.content) == ("user", "Hi there")
    assert (assistant.role, assistant.content) == ("assistant", "Hello world")
    assert str(assistant.id) == done["message_id"]
    assert assistant.prompt_ref == "chat_system@v1" and assistant.input_tokens == 10


async def test_history_is_sent_on_the_next_turn(client: AsyncClient, fake_gateway: FakeGateway):
    cid = str(uuid.uuid4())
    await chat(client, cid, "My name is Rutvik")
    await chat(client, cid, "What is my name?")

    second_call = fake_gateway.calls[1]
    assert [m.role for m in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[1].content == "My name is Rutvik"


async def test_model_error_becomes_error_event_and_question_is_kept(
    client: AsyncClient, fake_gateway: FakeGateway
):
    fake_gateway.chunks = []
    fake_gateway.error = LLMError("rate_limit", "Slow down", "fake", detail="429 from provider")
    cid = str(uuid.uuid4())
    events = await chat(client, cid, "Hello?")

    assert [e["type"] for e in events] == ["error", "done"]
    error = events[0]
    assert error["code"] == "rate_limit" and error["retryable"] is True
    assert "429" not in error["message"]  # provider detail stays in the logs
    assert events[1]["message_id"] is None
    assert [m.role for m in await saved_messages(cid)] == ["user"]


async def test_partial_answer_is_saved_but_left_out_of_history(
    client: AsyncClient, fake_gateway: FakeGateway
):
    fake_gateway.chunks = ["Half an ans"]
    fake_gateway.error = LLMError("timeout", "Too slow", "fake")
    cid = str(uuid.uuid4())
    await chat(client, cid, "Tell me something")
    assert (await saved_messages(cid))[-1].error_code == "timeout"

    fake_gateway.chunks, fake_gateway.error = ["ok"], None
    await chat(client, cid, "Again")
    roles = [m.role for m in fake_gateway.calls[-1]]
    assert roles == ["system", "user", "user"]  # the cut-off answer was not re-sent


async def test_unknown_model_is_rejected_before_streaming(client: AsyncClient):
    response = await client.post(
        "/api/chat",
        json={"conversation_id": str(uuid.uuid4()), "message": "hi", "model_id": "gpt-9"},
    )
    assert response.status_code == 400


async def test_empty_message_is_a_validation_error(client: AsyncClient):
    response = await client.post(
        "/api/chat", json={"conversation_id": str(uuid.uuid4()), "message": ""}
    )
    assert response.status_code == 422


async def test_conversation_endpoints_list_open_and_delete(client: AsyncClient):
    cid = str(uuid.uuid4())
    await chat(client, cid, "First question\nwith a second line")

    listed = (await client.get("/api/conversations")).json()
    assert listed[0]["id"] == cid and listed[0]["title"] == "First question"

    messages = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]

    assert (await client.delete(f"/api/conversations/{cid}")).status_code == 204
    assert (await client.get(f"/api/conversations/{cid}/messages")).status_code == 404
    assert await saved_messages(cid) == []  # messages went with it (ON DELETE CASCADE)
