"""Phase 6: images in chat. The gateway's image format, image checks, and the chat flow
(route to a vision model -> describe -> search -> answer) end to end with a fake LLM."""

import base64
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_catalog, get_chat_service, get_prompts, get_settings
from core.config import Settings
from core.db import get_session_factory
from core.images import ImageError, decode_image, sniff
from core.llm import ChatMessage, ImagePart, LLMError, LLMGateway, _dump_for_trace, _wire
from core.model_catalog import CatalogDefaults, ModelCatalog, ModelEntry
from core.multimodal_config import ImagesConfig, MultimodalConfig
from core.tracing import Tracer
from main import app
from services.chat_service import ChatService
from tests.conftest import FakeGateway, FakeRetriever
from tests.test_chat import sse_events

# A real 1x1 PNG.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kg"
    "AAAABJRU5ErkJggg=="
)  # fmt: skip
PNG = base64.b64decode(PNG_B64)


# ---------------------------------------------------------------------- image checks


def test_the_type_comes_from_the_bytes_not_the_label():
    assert sniff(PNG) == "image/png"
    assert sniff(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff(b"<html>not an image</html>") is None


def test_decode_image_rejects_non_images_bad_base64_and_big_files():
    raw, part = decode_image(PNG_B64, max_mb=1)
    assert raw == PNG and part.media_type == "image/png"
    with pytest.raises(ImageError, match="PNG, JPEG"):
        decode_image(base64.b64encode(b"just text").decode(), max_mb=1)
    with pytest.raises(ImageError, match="base64"):
        decode_image("not base64!!", max_mb=1)
    with pytest.raises(ImageError, match="at most"):
        decode_image(base64.b64encode(PNG + b"x" * 2_000_000).decode(), max_mb=1)


# ---------------------------------------------------------------------- gateway format


def test_images_go_to_the_model_as_content_parts_but_not_to_the_trace():
    image = ImagePart(media_type="image/png", data=PNG_B64)
    message = ChatMessage(role="user", content="What is this?", images=[image])
    wire = _wire(message)
    assert wire["content"][0] == {"type": "text", "text": "What is this?"}
    assert wire["content"][1]["image_url"]["url"].startswith("data:image/png;base64,iVBOR")
    traced = _dump_for_trace([message])[0]["content"]
    assert "base64" not in traced and "[image: image/png" in traced


def entry(model_id: str, vision: bool) -> ModelEntry:
    return ModelEntry(
        id=model_id, label=model_id.title(), provider="test", litellm_model=f"x/{model_id}",
        vision=vision,
    )  # fmt: skip


def test_a_text_only_model_refuses_images_clearly():
    image = ImagePart(media_type="image/png", data="")
    message = ChatMessage(role="user", content="?", images=[image])
    with pytest.raises(LLMError) as err:
        LLMGateway._check_images(entry("text", vision=False), [message])
    assert err.value.kind == "bad_request"
    LLMGateway._check_images(entry("eyes", vision=True), [message])  # no error


def test_the_vision_default_must_be_a_vision_model():
    entries = [entry("text", vision=False), entry("eyes", vision=True)]
    ModelCatalog(entries, CatalogDefaults(chat="text", cheap="text", vision="eyes"), Settings())
    with pytest.raises(ValueError, match="not a vision model"):
        ModelCatalog(entries, CatalogDefaults(chat="text", cheap="text", vision="text"), Settings())


# ---------------------------------------------------------------------- chat flow


class RecordingGateway(FakeGateway):
    """Also records which model each call went to."""

    def __init__(self) -> None:
        super().__init__(chunks=["A screenshot", " of the travel policy."])
        self.models: list[str] = []
        self.names: list[str] = []

    async def stream_chat(self, model_id, messages, *, trace=None, name="chat", prompt_ref=None):  # type: ignore[override]
        self.models.append(model_id)
        self.names.append(name)
        async for chunk in super().stream_chat(model_id, messages, trace=trace, name=name):
            yield chunk


@pytest.fixture
async def vision_client(
    db: None, fake_retriever: FakeRetriever
) -> AsyncIterator[tuple[AsyncClient, RecordingGateway]]:
    gateway = RecordingGateway()
    service = ChatService(
        gateway,
        get_prompts(),
        get_settings(),
        get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"),
        fake_retriever,
        top_k=5,
        catalog=get_catalog(),
        multimodal=MultimodalConfig(images=ImagesConfig(max_per_message=2, max_mb=1)),
    )
    app.dependency_overrides[get_chat_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, gateway
    app.dependency_overrides.clear()


def image_body(conversation_id: str, message: str, images: list[str]) -> dict:
    return {
        "conversation_id": conversation_id,
        "message": message,
        "model_id": "gpt-oss-cloud",  # text-only: the image must be routed elsewhere
        "images": [{"media_type": "image/png", "data": b} for b in images],
    }


async def test_image_question_is_routed_described_searched_and_answered(
    vision_client: tuple[AsyncClient, RecordingGateway], fake_retriever: FakeRetriever
):
    client, gateway = vision_client
    vision = get_catalog().defaults.vision
    conversation = str(uuid.uuid4())
    response = await client.post(
        "/api/chat", json=image_body(conversation, "What does this show?", [PNG_B64])
    )
    assert response.status_code == 200
    events = sse_events(response.text)
    steps = {e["step_id"]: e for e in events if e["type"] == "agent_step"}
    assert "can't read images" in steps["vision_route"]["detail"]
    assert steps["describe_image"]["detail"] == "A screenshot of the travel policy."
    # Two model calls, both on the vision model: describe, then answer.
    assert gateway.names == ["describe_image", "chat"] and gateway.models == [vision, vision]
    describe, answer = gateway.calls
    assert describe[0].images and describe[0].images[0].media_type == "image/png"
    assert answer[-1].role == "user" and answer[-1].images  # the answer model sees the image
    # Describe, then search: the description joins the query.
    assert fake_retriever.queries == ["What does this show?\nA screenshot of the travel policy."]
    assert events[-1]["type"] == "done" and events[-1]["usage"]["model_id"] == vision

    # Saved: the message lists its image, and the image is served with its real type.
    messages = (await client.get(f"/api/conversations/{conversation}/messages")).json()
    image = messages[0]["images"][0]
    assert image["description"] == "A screenshot of the travel policy."
    served = await client.get(f"/api/images/{image['id']}")
    assert served.content == PNG and served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"


async def test_a_follow_up_gets_the_earlier_image_as_text(
    vision_client: tuple[AsyncClient, RecordingGateway],
):
    client, gateway = vision_client
    conversation = str(uuid.uuid4())
    await client.post("/api/chat", json=image_body(conversation, "What does this show?", [PNG_B64]))
    gateway.calls.clear()
    await client.post("/api/chat", json={"conversation_id": conversation, "message": "And then?"})
    history = gateway.calls[-1]
    first_question = next(m for m in history if m.role == "user")
    assert "[Attached image: A screenshot of the travel policy.]" in first_question.content
    assert not any(m.images for m in history)  # only the current question's images are sent


@pytest.mark.parametrize(
    ("images", "detail"),
    [
        ([base64.b64encode(b"<svg>no</svg>").decode()], "PNG, JPEG"),
        ([PNG_B64, PNG_B64, PNG_B64], "At most 2 images"),
    ],
)
async def test_bad_images_are_rejected_before_streaming(
    vision_client: tuple[AsyncClient, RecordingGateway], images: list[str], detail: str
):
    client, gateway = vision_client
    response = await client.post("/api/chat", json=image_body(str(uuid.uuid4()), "Hi", images))
    assert response.status_code == 400 and detail in response.json()["detail"]
    assert gateway.calls == []


async def test_unknown_image_id_is_404(vision_client: tuple[AsyncClient, RecordingGateway]):
    client, _ = vision_client
    assert (await client.get(f"/api/images/{uuid.uuid4()}")).status_code == 404
