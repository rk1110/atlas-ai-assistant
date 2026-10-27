"""The streaming contract. The drift tests here keep three copies of it in sync:
core/events.py (Python), core/llm.py (error kinds) and frontend/lib/events.ts (TypeScript)."""

import json
import re
from typing import get_args

import pytest

from core.config import REPO_ROOT
from core.events import (
    AgentStepEvent,
    ApprovalRequestEvent,
    CitationEvent,
    DoneEvent,
    ErrorCode,
    ErrorEvent,
    TokenEvent,
    ToolCallEvent,
    Usage,
    stream_event_adapter,
    to_sse,
)
from core.llm import LLMErrorKind

EXAMPLES = [
    TokenEvent(text="hi"),
    CitationEvent(citation_id="1", document_id="d", title="T", snippet="s"),
    AgentStepEvent(step_id="s", agent="planner", status="started", title="Plan"),
    ToolCallEvent(call_id="c", tool_name="calc", status="completed", input={"x": 1}, output=2),
    ApprovalRequestEvent(approval_id="a", tool_name="create_ticket", summary="s", payload={}),
    ErrorEvent(code="rate_limit", message="slow down", retryable=True),
    DoneEvent(
        message_id="m",
        usage=Usage(
            model_id="x",
            input_tokens=1,
            output_tokens=2,
            cost_usd=None,
            latency_ms=3,
            time_to_first_token_ms=None,
        ),
        prompt_ref="chat_system@v1",
    ),
]
TS_EVENTS = (
    (REPO_ROOT / "frontend" / "lib" / "events.ts").read_text()
    if (REPO_ROOT / "frontend" / "lib" / "events.ts").exists()
    else None
)


@pytest.mark.parametrize("event", EXAMPLES, ids=lambda e: e.type)
def test_every_event_round_trips_through_json(event):
    assert stream_event_adapter.validate_json(event.model_dump_json()) == event


def test_sse_frame_format():
    frame = to_sse(TokenEvent(text="hi"))
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    assert json.loads(frame[len("data: ") :]) == {"type": "token", "text": "hi"}


def test_every_llm_error_kind_is_a_valid_error_code():
    # Would have caught the 3a bug where "billing" existed in one list but not the other.
    assert set(get_args(LLMErrorKind)) <= set(get_args(ErrorCode))


@pytest.mark.skipif(TS_EVENTS is None, reason="frontend/ not available")
def test_typescript_event_types_match_python():
    ts_list = re.search(r"STREAM_EVENT_TYPES = \[(.*?)\]", TS_EVENTS, re.DOTALL).group(1)
    assert set(re.findall(r'"(\w+)"', ts_list)) == {e.type for e in EXAMPLES}


@pytest.mark.skipif(TS_EVENTS is None, reason="frontend/ not available")
def test_typescript_error_codes_match_python():
    ts_union = re.search(r"export type ErrorCode =(.*?);", TS_EVENTS, re.DOTALL).group(1)
    assert set(re.findall(r'"(\w+)"', ts_union)) == set(get_args(ErrorCode))
