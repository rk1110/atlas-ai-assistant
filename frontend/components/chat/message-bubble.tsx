"use client";

import { motion } from "motion/react";

import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { CitationList } from "@/components/chat/citation-list";
import { ErrorBanner } from "@/components/chat/error-banner";
import { MessageMeta } from "@/components/chat/message-meta";
import { MessageSteps } from "@/components/chat/message-steps";
import type { ChatMessage } from "@/lib/use-chat-stream";

/** One message. User text is shown as typed; assistant text is Markdown with source chips. */
export function MessageBubble({ message, onRetry }: { message: ChatMessage; onRetry?: () => void }) {
  // Only new messages fade in. History must be visible in the server-rendered HTML, before
  // JavaScript loads; `initial={false}` renders it at its final state.
  const enter = message.live ? { opacity: 0, y: 6 } : false;
  if (message.role === "user") {
    return (
      <motion.div initial={enter} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </div>
      </motion.div>
    );
  }

  const waiting = message.status === "streaming" && message.content === "";
  return (
    <motion.div initial={enter} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-2">
      <MessageSteps steps={message.steps} />
      {waiting ? (
        <ThinkingDots />
      ) : (
        message.content && <AnswerMarkdown content={message.content} citations={message.citations} />
      )}
      <CitationList citations={message.citations} />
      {message.status === "stopped" && <p className="text-xs text-muted-foreground">Stopped.</p>}
      {message.error && <ErrorBanner error={message.error} onRetry={onRetry} />}
      {message.status !== "streaming" && <MessageMeta usage={message.usage} traceUrl={message.traceUrl} />}
    </motion.div>
  );
}

/** Shown until the first token arrives (models can think for a few seconds first). */
function ThinkingDots() {
  return (
    <div className="flex h-6 items-center gap-1" role="status" aria-label="Atlas is thinking">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="size-1.5 rounded-full bg-muted-foreground"
          animate={{ opacity: [0.25, 1, 0.25] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </div>
  );
}
