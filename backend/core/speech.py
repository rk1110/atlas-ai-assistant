"""Speech-to-text: the one place that turns recorded audio into a question (Phase 6).

Whisper is a speech model from OpenAI, released as open weights: an encoder listens to 30-second
windows of audio (as a spectrogram, a picture of which frequencies are loud over time) and a
decoder writes the words, like an LLM writing text. faster-whisper runs the same weights on
CTranslate2, an inference engine that is ~4x faster than the original on CPU.

Why local, not an API: free, private (the recording never leaves the backend), and a few
seconds of speech transcribe in about a second on a laptop CPU. Like embeddings, it's not an
LLM call, so it doesn't go through the LiteLLM gateway; it gets its own Langfuse trace instead.

    browser (MediaRecorder: webm/opus or mp4) -> POST /api/voice/transcribe
      -> decode to 16 kHz mono (PyAV, ffmpeg inside) -> check length -> Whisper -> text
"""

import logging
import threading
import time
from functools import lru_cache
from io import BytesIO
from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel

from core.multimodal_config import VoiceConfig, get_multimodal_config

if TYPE_CHECKING:
    import numpy as np
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000  # Whisper was trained on 16 kHz audio


class TranscriptionError(ValueError):
    """Audio we can't transcribe. The message is safe to show the user."""


class SpeechModelUnavailableError(RuntimeError):
    """The Whisper model couldn't be loaded (usually: not downloaded yet, and offline)."""


class Transcript(BaseModel):
    text: str
    language: str
    duration_seconds: float
    latency_ms: int


class Transcriber:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> "WhisperModel":
        """Loaded on first use (the first recording waits a few seconds; the first ever also
        downloads the model into the hf_cache volume)."""
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # heavy import

                logger.info("loading whisper model %s", self.config.model)
                self._model = WhisperModel(
                    self.config.model, device="cpu", compute_type=self.config.compute_type
                )
        return self._model

    async def transcribe(self, audio: bytes) -> Transcript:
        # Decoding and the model are CPU-bound: run them in a worker thread.
        return await anyio.to_thread.run_sync(self._transcribe, audio)

    def _transcribe(self, audio: bytes) -> Transcript:
        started = time.perf_counter()
        samples = _decode(audio)
        duration = len(samples) / SAMPLE_RATE
        if duration < 0.3:
            raise TranscriptionError("The recording is empty. Hold the mic a little longer.")
        if duration > self.config.max_seconds:
            raise TranscriptionError(
                f"Recordings can be at most {self.config.max_seconds:g} seconds."
            )
        try:
            model = self.model
        except Exception as exc:
            logger.exception("could not load whisper model %s", self.config.model)
            raise SpeechModelUnavailableError(
                f"The speech model (whisper {self.config.model}) isn't available. If "
                "HF_HUB_OFFLINE=1, download it once with HF_HUB_OFFLINE=0 (see docs)."
            ) from exc
        segments, info = model.transcribe(
            samples,
            language=self.config.language,
            beam_size=self.config.beam_size,
            # Voice activity detection (a small model, Silero VAD) cuts silence first. Without
            # it, Whisper sometimes "hears" words in silence ("Thank you for watching!").
            vad_filter=True,
            # Primes the decoder with Atlas's vocabulary (see config/multimodal.yaml).
            initial_prompt=self.config.prompt,
        )
        # `segments` is lazy: transcription actually runs while we iterate.
        text = " ".join(s.text.strip() for s in segments).strip()
        return Transcript(
            text=text,
            language=info.language,
            duration_seconds=round(duration, 2),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _decode(audio: bytes) -> "np.ndarray":
    """Any browser format -> 16 kHz mono float samples. Not-audio raises TranscriptionError."""
    from faster_whisper.audio import decode_audio

    try:
        return decode_audio(BytesIO(audio), sampling_rate=SAMPLE_RATE)
    except Exception as exc:  # PyAV raises many error types for corrupt or non-audio data
        raise TranscriptionError("That doesn't look like an audio recording.") from exc


@lru_cache
def get_transcriber() -> Transcriber:
    return Transcriber(get_multimodal_config().voice)
