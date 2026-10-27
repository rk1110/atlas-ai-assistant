"use client";

/**
 * useChatStream: sends a chat message and reads the answer as a Server-Sent Events stream.
 *
 * Why not the browser's built-in EventSource: it only supports GET, and we must POST the
 * message. So we use fetch() and read the response body ourselves:
 *
 *   bytes ──TextDecoder──▶ text ──split on "\n\n"──▶ frames ──"data: {json}"──▶ StreamEvent
 *
 * Network packets don't line up with events (one read can hold half an event, or three), so
 * incomplete text stays in `buffer` until its blank-line terminator arrives.
 */

import { useCallback, useRef, useState } from "react";

import { BROWSER_API_URL } from "@/lib/api";
import { type ErrorEvent, parseStreamEvent, type StreamEvent, type Usage } from "@/lib/events";

export type MessageStatus = "streaming" | "done" | "error" | "stopped";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  error: ErrorEvent | null;
  usage: Usage | null;
  traceUrl: string | null;
  modelId: string | null;
  /** true for messages created during this visit: only those animate in. */
  live: boolean;
}

interface Options {
  /** Called when a message is sent, so a new chat can create its id at that moment. */
  getConversationId: () => string;
  initialMessages: ChatMessage[];
  /** Called once per finished turn (done, error or stop), e.g. to refresh the sidebar. */
  onTurnEnd?: () => void;
}

export function useChatStream({ getConversationId, initialMessages, onTurnEnd }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const updateMessage = useCallback((id: string, change: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? change(m) : m)));
  }, []);

  const send = useCallback(
    async (text: string, modelId: string | null) => {
      const userId = crypto.randomUUID();
      // Temporary id until the `done` event tells us the id the backend saved it under.
      let assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { ...blank(userId, "user", modelId), content: text, status: "done" },
        blank(assistantId, "assistant", modelId),
      ]);
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      const handle = (event: StreamEvent) => {
        switch (event.type) {
          case "token":
            updateMessage(assistantId, (m) => ({ ...m, content: m.content + event.text }));
            break;
          case "error":
            updateMessage(assistantId, (m) => ({ ...m, status: "error", error: event }));
            break;
          case "done": {
            const savedId = event.message_id;
            updateMessage(assistantId, (m) => ({
              ...m,
              id: savedId ?? m.id,
              status: m.status === "streaming" ? "done" : m.status,
              usage: event.usage,
              traceUrl: event.trace_url,
            }));
            if (savedId) assistantId = savedId;
            break;
          }
          case "citation":
          case "agent_step":
          case "tool_call":
          case "approval_request":
            break; // Phase 2+ events: the UI for these arrives with those phases.
        }
      };

      try {
        const response = await fetch(`${BROWSER_API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ conversation_id: getConversationId(), message: text, model_id: modelId }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          // Rejected before streaming started (400 unknown model, 422 invalid input).
          handle(httpError(response.status, await response.text()));
          return;
        }
        await readEvents(response.body, handle);
      } catch {
        if (controller.signal.aborted) {
          // The user pressed Stop. The backend saves the partial answer as "cancelled".
          updateMessage(assistantId, (m) => ({ ...m, status: "stopped" }));
        } else {
          handle({
            type: "error",
            code: "internal",
            message: "Couldn't reach Atlas. Check that the backend is running.",
            retryable: true,
          });
        }
      } finally {
        // Safety net: a stream that ended without `done` must not stay "streaming" forever.
        updateMessage(assistantId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
        setIsStreaming(false);
        abortRef.current = null;
        onTurnEnd?.();
      }
    },
    [getConversationId, onTurnEnd, updateMessage],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, isStreaming, send, stop };
}

/** Read an SSE body and call `onEvent` for every complete `data:` frame. */
async function readEvents(body: ReadableStream<Uint8Array>, onEvent: (e: StreamEvent) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }); // stream: keep split UTF-8 chars intact
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      const event = data ? parseStreamEvent(data) : null;
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function blank(id: string, role: ChatMessage["role"], modelId: string | null): ChatMessage {
  return { id, role, content: "", status: "streaming", error: null, usage: null, traceUrl: null, modelId, live: true };
}

function httpError(status: number, body: string): ErrorEvent {
  let message = `Request rejected (HTTP ${status}).`;
  try {
    const detail: unknown = JSON.parse(body).detail;
    if (typeof detail === "string") message = detail;
  } catch {
    // keep the generic message
  }
  return { type: "error", code: status === 422 ? "validation" : "bad_request", message, retryable: false };
}
