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
 *
 * Phase 4: an agent turn can pause on an approval card. `respond()` sends the decision to
 * POST /api/chat/approval and streams the rest of the turn into the SAME answer bubble.
 */

import { useCallback, useRef, useState } from "react";

import { type ActivityEntry, BROWSER_API_URL, loginUrl } from "@/lib/api";
import type { AttachedImage } from "@/lib/images";
import {
  type AgentStepEvent,
  type ApprovalRequestEvent,
  type CitationEvent,
  type ErrorEvent,
  parseStreamEvent,
  type StreamEvent,
  type ToolCallEvent,
  type Usage,
} from "@/lib/events";

export type MessageStatus = "streaming" | "done" | "error" | "stopped";

export type ApprovalState = "pending" | "sending" | "approved" | "rejected";

/** An approval card: the request, plus what the human did with it. */
export interface Approval extends ApprovalRequestEvent {
  state: ApprovalState;
}

export type ApprovalDecision = "approve" | "reject";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  error: ErrorEvent | null;
  /** Sources the answer cited; they arrive after the last token. */
  citations: CitationEvent[];
  /** Steps taken before answering, e.g. "Searched for: <rewritten question>" (Phase 3). */
  steps: AgentStepEvent[];
  /** Tools the agent used, latest status per call (Phase 4). */
  toolCalls: ToolCallEvent[];
  /** Actions waiting for (or answered by) the human (Phase 4). */
  approvals: Approval[];
  /** Every agent event in arrival order with its time: the Activity Panel's timeline. */
  activity: ActivityEntry[];
  usage: Usage | null;
  traceUrl: string | null;
  modelId: string | null;
  /** Images attached to a user message (Phase 6). */
  images: AttachedImage[];
  /** true for messages created during this visit: only those animate in. */
  live: boolean;
}

interface Options {
  /** Called when a message is sent, so a new chat can create its id at that moment. */
  getConversationId: () => string;
  initialMessages: ChatMessage[];
  /** Called once per finished turn (done, error or stop), e.g. to refresh the sidebar. */
  onTurnEnd?: (outcome: { failed: boolean }) => void;
}

export function useChatStream({ getConversationId, initialMessages, onTurnEnd }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const updateMessage = useCallback((id: string, change: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? change(m) : m)));
  }, []);

  /** POST `body` to `path` and apply the SSE events to the assistant message `targetId`. */
  const streamInto = useCallback(
    async (path: string, body: unknown, targetId: string) => {
      let assistantId = targetId;
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      let failed = false;

      const handle = (event: StreamEvent) => {
        if (event.type === "agent_step" || event.type === "tool_call" || event.type === "approval_request") {
          const entry = { at: new Date().toISOString(), event };
          updateMessage(assistantId, (m) => ({ ...m, activity: [...m.activity, entry] }));
        }
        switch (event.type) {
          case "token":
            updateMessage(assistantId, (m) => ({ ...m, content: m.content + event.text }));
            break;
          case "error":
            failed = true;
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
            updateMessage(assistantId, (m) => ({ ...m, citations: [...m.citations, event] }));
            break;
          case "agent_step":
            updateMessage(assistantId, (m) => ({ ...m, steps: [...m.steps, event] }));
            break;
          case "tool_call":
            // started -> completed/failed arrive as separate events for one call_id: keep the latest.
            updateMessage(assistantId, (m) => ({
              ...m,
              toolCalls: m.toolCalls.some((c) => c.call_id === event.call_id)
                ? m.toolCalls.map((c) => (c.call_id === event.call_id ? event : c))
                : [...m.toolCalls, event],
            }));
            break;
          case "approval_request":
            updateMessage(assistantId, (m) => ({ ...m, approvals: [...m.approvals, { ...event, state: "pending" }] }));
            break;
        }
      };

      try {
        const response = await fetch(`${BROWSER_API_URL}${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
          credentials: "include", // the session cookie (Phase 7)
        });
        if (response.status === 401) {
          window.location.assign(loginUrl());
          return;
        }
        if (!response.ok || !response.body) {
          // Rejected before streaming started (400 unknown model, 404 stale approval, 422 invalid input).
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
        onTurnEnd?.({ failed });
      }
    },
    [onTurnEnd, updateMessage],
  );

  const send = useCallback(
    async (
      text: string,
      modelId: string | null,
      { retry = false, images = [] }: { retry?: boolean; images?: AttachedImage[] } = {},
    ) => {
      // Temporary id until the `done` event tells us the id the backend saved it under.
      const assistantId = crypto.randomUUID();
      setMessages((prev) =>
        retry
          ? // Try again: the question is already on screen (and saved). Swap the failed answer
            // for a fresh one instead of adding the question a second time.
            [...prev.filter((m) => !(m === prev.at(-1) && m.status === "error")), blank(assistantId, "assistant", modelId)]
          : [
              ...prev,
              { ...blank(crypto.randomUUID(), "user", modelId), content: text, status: "done", images },
              blank(assistantId, "assistant", modelId),
            ],
      );
      await streamInto(
        "/api/chat",
        {
          conversation_id: getConversationId(),
          message: text,
          model_id: modelId,
          retry,
          // A retry sends none: the backend re-reads the images saved with the question.
          images: images.map((i) => ({ media_type: i.mediaType, data: i.data })),
        },
        assistantId,
      );
    },
    [getConversationId, streamInto],
  );

  /** Answer an approval card: the agent resumes and the turn continues in the same bubble. */
  const respond = useCallback(
    async (messageId: string, approvalId: string, decision: ApprovalDecision, args?: Record<string, unknown>) => {
      const owner = messages.find((m) => m.id === messageId);
      if (!owner) return;
      updateMessage(messageId, (m) => ({
        ...m,
        status: "streaming",
        error: null,
        approvals: m.approvals.map((a) =>
          a.approval_id === approvalId ? { ...a, state: decision === "approve" ? "approved" : "rejected" } : a,
        ),
      }));
      await streamInto(
        "/api/chat/approval",
        {
          conversation_id: getConversationId(),
          approval_id: approvalId,
          decision,
          args: args ?? null,
          model_id: owner.modelId,
        },
        messageId,
      );
    },
    [getConversationId, messages, streamInto, updateMessage],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, isStreaming, send, respond, stop };
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
  return {
    id,
    role,
    content: "",
    status: "streaming",
    error: null,
    citations: [],
    steps: [],
    toolCalls: [],
    approvals: [],
    activity: [],
    usage: null,
    traceUrl: null,
    modelId,
    images: [],
    live: true,
  };
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
