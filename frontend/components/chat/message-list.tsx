"use client";

import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/message-bubble";
import type { ApprovalDecision, ChatMessage } from "@/lib/use-chat-stream";

/** The conversation. Keeps the newest text in view while an answer streams in. */
export function MessageList({
  messages,
  onRetry,
  onRespond,
  isStreaming,
}: {
  messages: ChatMessage[];
  onRetry: () => void;
  onRespond: (messageId: string, approvalId: string, decision: ApprovalDecision, args?: Record<string, unknown>) => void;
  isStreaming: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages.at(-1);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, last?.content.length, last?.toolCalls.length, last?.approvals.length]);

  return (
    <div className="flex flex-col gap-6">
      {messages.map((m) => (
        // Retry is offered only on the latest answer: it re-sends the last question.
        <MessageBubble
          key={m.id}
          message={m}
          onRetry={m.id === last?.id ? onRetry : undefined}
          onRespond={(approvalId, decision, args) => onRespond(m.id, approvalId, decision, args)}
          busy={isStreaming}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}
