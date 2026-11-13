"use client";

import { motion } from "motion/react";

import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { ApprovalCard } from "@/components/chat/approval-card";
import { CitationList } from "@/components/chat/citation-list";
import { ErrorBanner } from "@/components/chat/error-banner";
import { ImageThumbnails } from "@/components/chat/image-thumbnails";
import { MessageMeta } from "@/components/chat/message-meta";
import { MessageSteps } from "@/components/chat/message-steps";
import { SpeakButton } from "@/components/chat/speak-button";
import { ToolCallList } from "@/components/chat/tool-call-list";
import type { ApprovalDecision, ChatMessage } from "@/lib/use-chat-stream";

export type RespondHandler = (approvalId: string, decision: ApprovalDecision, args?: Record<string, unknown>) => void;

/** One message. User text is shown as typed; assistant text is Markdown with source chips. */
export function MessageBubble({
  message,
  onRetry,
  onRespond,
  busy = false,
}: {
  message: ChatMessage;
  onRetry?: () => void;
  onRespond?: RespondHandler;
  /** Another answer is streaming: approval buttons wait. */
  busy?: boolean;
}) {
  // Only new messages fade in. History must be visible in the server-rendered HTML, before
  // JavaScript loads; `initial={false}` renders it at its final state.
  const enter = message.live ? { opacity: 0, y: 6 } : false;
  if (message.role === "user") {
    return (
      <motion.div initial={enter} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-end gap-1.5">
        <ImageThumbnails images={message.images} className="justify-end" />
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </div>
      </motion.div>
    );
  }

  const waiting = message.status === "streaming" && message.content === "" && message.toolCalls.length === 0;
  return (
    <motion.div initial={enter} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-2">
      <MessageSteps steps={message.steps} />
      <ToolCallList calls={message.toolCalls} />
      {message.approvals.map((approval) => (
        <ApprovalCard
          key={approval.approval_id}
          approval={approval}
          disabled={busy || !onRespond}
          onRespond={(decision, args) => onRespond?.(approval.approval_id, decision, args)}
        />
      ))}
      {waiting ? (
        <ThinkingDots />
      ) : (
        message.content && <AnswerMarkdown content={message.content} citations={message.citations} />
      )}
      <CitationList citations={message.citations} />
      {message.status === "stopped" && <p className="text-xs text-muted-foreground">Stopped.</p>}
      {message.error && <ErrorBanner error={message.error} onRetry={onRetry} />}
      {message.status !== "streaming" && (
        <div className="flex items-center gap-1">
          <SpeakButton id={message.id} text={message.content} />
          <MessageMeta usage={message.usage} traceUrl={message.traceUrl} />
        </div>
      )}
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
