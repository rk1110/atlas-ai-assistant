"""POST /api/classify: structured-output demo. Returns a validated intent label as JSON."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import CatalogDep, ClassifierDep, TracerDep
from core.events import Usage
from core.llm import LLMError
from services.intent import Intent

router = APIRouter(prefix="/api", tags=["classify"])

# HTTP status per error kind: client mistakes are 4xx, provider trouble is 502/503.
STATUS_BY_KIND = {
    "unknown_model": 400, "unavailable": 503, "billing": 402, "rate_limit": 429,
    "timeout": 504, "invalid_output": 502,
}  # fmt: skip


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None  # None = the catalog's cheap model


class ClassifyResponse(BaseModel):
    intent: Intent
    confidence: float
    reasoning: str
    prompt_ref: str
    usage: Usage
    trace_url: str | None


@router.post("/classify")
async def classify(
    request: ClassifyRequest, classifier: ClassifierDep, catalog: CatalogDep, tracer: TracerDep
) -> ClassifyResponse:
    if request.model_id and catalog.get(request.model_id) is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{request.model_id}'")
    try:
        result = await classifier.classify(request.message, request.model_id)
    except LLMError as err:
        raise HTTPException(
            status_code=STATUS_BY_KIND.get(err.kind, 502),
            detail={"code": err.kind, "message": err.message},
        ) from err
    c, completion = result.classification, result.completion
    return ClassifyResponse(
        intent=c.intent,
        confidence=c.confidence,
        reasoning=c.reasoning,
        prompt_ref=result.prompt_ref,
        usage=Usage(
            model_id=completion.model_id,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=completion.cost_usd,
            latency_ms=completion.latency_ms,
            time_to_first_token_ms=None,
        ),
        trace_url=tracer.trace_url(completion.trace_id),
    )
