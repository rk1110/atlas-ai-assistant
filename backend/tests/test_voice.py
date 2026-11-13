"""Phase 6 checkpoint C: speech-to-text. Audio decoding is real (PyAV on an eval clip); the
Whisper model is replaced by a fake so tests stay fast and offline."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from core.multimodal_config import VoiceConfig
from core.speech import SAMPLE_RATE, Transcriber, TranscriptionError, _decode, get_transcriber
from evals.voice_run import CLIPS_DIR, word_error_rate
from main import app

CLIP = (CLIPS_DIR / "badge-lost.wav").read_bytes()


class FakeWhisper:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def transcribe(self, samples, **kwargs):  # type: ignore[no-untyped-def]
        self.kwargs = kwargs
        segments = [
            SimpleNamespace(text=" I lost my office badge."),
            SimpleNamespace(text=" Help?"),
        ]
        return iter(segments), SimpleNamespace(language="en")


def fake_transcriber(**config: object) -> tuple[Transcriber, FakeWhisper]:
    transcriber = Transcriber(VoiceConfig(prompt="Acme and Jira.", **config))  # type: ignore[arg-type]
    whisper = FakeWhisper()
    transcriber._model = whisper  # type: ignore[assignment]
    return transcriber, whisper


def test_word_error_rate_counts_word_edits_ignoring_case_and_punctuation():
    assert word_error_rate("Open a Jira ticket.", "open a jira ticket") == 0
    assert word_error_rate("Open a Jira ticket", "Open age era ticket") == 0.5  # 1 sub + 1 ins
    assert word_error_rate("What are the values", "What the values") == 0.25  # 1 deletion


def test_browser_audio_is_decoded_to_16khz_and_non_audio_is_refused():
    samples = _decode(CLIP)
    assert 1.5 < len(samples) / SAMPLE_RATE < 5  # a ~2.7 s spoken question
    with pytest.raises(TranscriptionError, match="audio recording"):
        _decode(b"definitely not audio")


async def test_transcribe_joins_segments_and_primes_with_the_prompt():
    transcriber, whisper = fake_transcriber()
    transcript = await transcriber.transcribe(CLIP)
    assert transcript.text == "I lost my office badge. Help?"
    assert transcript.language == "en" and transcript.duration_seconds > 1
    assert whisper.kwargs["initial_prompt"] == "Acme and Jira."
    assert whisper.kwargs["vad_filter"] is True


async def test_recordings_over_the_limit_are_refused():
    transcriber, _ = fake_transcriber(max_seconds=1)
    with pytest.raises(TranscriptionError, match="at most 1 seconds"):
        await transcriber.transcribe(CLIP)


@pytest.fixture
async def voice_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    transcriber, _ = fake_transcriber(max_mb=0.05)  # ~50 KB: the clip fits, 100 KB doesn't
    app.dependency_overrides[get_transcriber] = lambda: transcriber
    yield client
    app.dependency_overrides.pop(get_transcriber)


async def post(client: AsyncClient, data: bytes):
    files = {"audio": ("question.webm", data, "audio/webm")}
    return await client.post("/api/voice/transcribe", files=files)


async def test_transcribe_endpoint(voice_client: AsyncClient):
    ok = await post(voice_client, CLIP[:48_000])
    assert ok.status_code == 200 and ok.json()["text"] == "I lost my office badge. Help?"
    bad = await post(voice_client, b"not audio")
    assert bad.status_code == 400 and "audio recording" in bad.json()["detail"]
    big = await post(voice_client, b"x" * 100_000)
    assert big.status_code == 413
