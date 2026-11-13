import type { StoredMessage } from "@/lib/api";
import { storedImage } from "@/lib/images";
import type { ChatMessage } from "@/lib/use-chat-stream";

/** Convert a message loaded from the database into the shape the chat UI renders. */
export function toChatMessage(m: StoredMessage): ChatMessage {
  // "awaiting_approval": an agent turn paused on an approval card (Phase 4), not a failure.
  const failed = m.error_code !== null && m.error_code !== "cancelled" && m.error_code !== "awaiting_approval";
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    status: m.error_code === "cancelled" ? "stopped" : failed ? "error" : "done",
    error: failed
      ? { type: "error", code: "internal", message: "This answer was cut off by an error.", retryable: false }
      : null,
    citations: m.citations,
    steps: m.agent?.steps ?? [], // agent answers save their steps; Phase 3 rewrites aren't saved
    toolCalls: m.agent?.tool_calls ?? [],
    approvals: m.agent?.approvals ?? [],
    activity: m.agent?.timeline ?? [],
    usage:
      m.input_tokens !== null && m.output_tokens !== null && m.latency_ms !== null && m.model_id
        ? {
            model_id: m.model_id,
            input_tokens: m.input_tokens,
            output_tokens: m.output_tokens,
            latency_ms: m.latency_ms,
            cost_usd: null,
            time_to_first_token_ms: null,
          }
        : null,
    traceUrl: m.trace_url,
    modelId: m.model_id,
    images: (m.images ?? []).map(storedImage),
    live: false, // history renders immediately, without a fade-in
  };
}
