"""POST /api/voice/transcribe: a recorded question -> text (Phase 6).

The text goes back into the message box, not straight into the chat: speech recognition
makes mistakes ("Acme" heard as "acne"), and the user should see and fix them before asking.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from api.deps import RateLimitedUserDep, TracerDep
from core.speech import (
    SpeechModelUnavailableError,
    Transcriber,
    Transcript,
    TranscriptionError,
    get_transcriber,
)

router = APIRouter(prefix="/api/voice", tags=["voice"])

TranscriberDep = Annotated[Transcriber, Depends(get_transcriber)]


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile, transcriber: TranscriberDep, tracer: TracerDep, user: RateLimitedUserDep
) -> Transcript:
    max_bytes = int(transcriber.config.max_mb * 1024 * 1024)
    data = await audio.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Recordings can be at most {transcriber.config.max_mb:g} MB",
        )
    trace = tracer.start_trace(
        "transcribe",
        input={"type": audio.content_type, "kb": len(data) // 1024},
        metadata={"model": f"whisper-{transcriber.config.model}"},
        user_id=str(user.id),
    )
    try:
        transcript = await transcriber.transcribe(data)
    except TranscriptionError as exc:
        trace.finish(error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except SpeechModelUnavailableError as exc:
        trace.finish(error=str(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    trace.finish(output=transcript.model_dump())
    return transcript
