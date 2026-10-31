/**
 * The streaming event contract: an exact TypeScript mirror of backend/core/events.py.
 *
 * Every chat answer arrives as a stream of these events over Server-Sent Events. The `type`
 * field is the discriminator: in a `switch (event.type)`, TypeScript narrows `event` to the
 * matching interface, so `event.text` only type-checks inside `case "token"`.
 *
 * Rules: same `type` strings, same field names, same nullability as the Python models.
 * Pydantic always serializes optional fields (as null), so optional Python fields are
 * `T | null` here, never `field?: T`.
 */

// ------------------------------------------------------------------ Phase 1: used now

export interface TokenEvent {
  type: "token";
  text: string;
}

export type ErrorCode =
  // Model/provider problems (mirrors core.llm.LLMErrorKind)
  | "unknown_model"
  | "unavailable"
  | "auth"
  | "rate_limit"
  | "bad_request"
  | "context_too_long"
  | "refusal"
  | "timeout"
  | "billing"
  | "invalid_output"
  | "provider_error"
  // Atlas's own problems
  | "validation"
  | "internal";

export interface ErrorEvent {
  type: "error";
  code: ErrorCode;
  message: string; // safe to show to the user
  retryable: boolean; // show "Try again" only when it can help
}

export interface Usage {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  time_to_first_token_ms: number | null;
}

export interface DoneEvent {
  type: "done";
  message_id: string | null;
  usage: Usage | null;
  prompt_ref: string | null;
  trace_id: string | null;
  trace_url: string | null;
}

// ------------------------------------------------------------------ Phase 2: citations

export interface CitationEvent {
  type: "citation";
  citation_id: string;
  document_id: string;
  title: string;
  heading: string | null; // e.g. "Values > Iteration"
  url: string | null;
  snippet: string;
  score: number | null;
}

// ------------------------------------------------------------------ Phase 4+: defined now, used later

export type StepStatus = "started" | "completed" | "failed";

export interface AgentStepEvent {
  type: "agent_step";
  step_id: string;
  agent: string;
  status: StepStatus;
  title: string;
  detail: string | null;
}

export interface ToolCallEvent {
  type: "tool_call";
  call_id: string;
  tool_name: string;
  status: StepStatus;
  /** One line for humans, e.g. "Create a high-priority IT ticket: “Broken screen”". */
  summary: string | null;
  input: Record<string, unknown>;
  output: unknown;
  error: string | null;
}

export interface ApprovalRequestEvent {
  type: "approval_request";
  approval_id: string;
  tool_name: string;
  summary: string;
  payload: Record<string, unknown>;
}

// ------------------------------------------------------------------ The union + parsing

export type StreamEvent =
  | TokenEvent
  | CitationEvent
  | AgentStepEvent
  | ToolCallEvent
  | ApprovalRequestEvent
  | ErrorEvent
  | DoneEvent;

export const STREAM_EVENT_TYPES = [
  "token",
  "citation",
  "agent_step",
  "tool_call",
  "approval_request",
  "error",
  "done",
] as const satisfies readonly StreamEvent["type"][];

/**
 * Parse one SSE `data:` payload. Returns null for anything that isn't a known event, so a
 * newer backend sending an event type this frontend doesn't know yet can't crash the page.
 */
export function parseStreamEvent(json: string): StreamEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    return null;
  }
  if (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    (STREAM_EVENT_TYPES as readonly unknown[]).includes(value.type)
  ) {
    return value as StreamEvent;
  }
  return null;
}
