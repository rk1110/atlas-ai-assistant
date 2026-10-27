"use client";

import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/message-bubble";
import type { ChatMessage } from "@/lib/use-chat-stream";

/** The conversation. Keeps the newest text in view while an answer streams in. */
export function MessageList({ messages, onRetry }: { messages: ChatMessage[]; onRetry: () => void }) {
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages.at(-1);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, last?.content.length]);

  return (
    <div className="flex flex-col gap-6">
      {messages.map((m) => (
        // Retry is offered only on the latest answer: it re-sends the last question.
        <MessageBubble key={m.id} message={m} onRetry={m.id === last?.id ? onRetry : undefined} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
