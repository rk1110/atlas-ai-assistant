"use client";

import { MotionConfig } from "motion/react";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { Composer } from "@/components/chat/composer";
import { EmptyState } from "@/components/chat/empty-state";
import { MessageList } from "@/components/chat/message-list";
import { ModelSwitcher } from "@/components/chat/model-switcher";
import { PageHeader } from "@/components/page-header";
import { notifyConversationsChanged } from "@/lib/api";
import { type ChatMessage, useChatStream } from "@/lib/use-chat-stream";

interface Props {
  /** null on the "New chat" page: an id is generated in the browser. */
  conversationId: string | null;
  title: string;
  initialMessages: ChatMessage[];
}

/**
 * The chat page. A Client Component: it holds state that changes many times per second while
 * tokens stream in. Server Components render the data it starts with (initialMessages).
 */
export function ChatView({ conversationId, title, initialMessages }: Props) {
  const router = useRouter();
  // A new chat gets its id on the first Send (an event), not while rendering: Next.js
  // prerenders pages, and a random value created during render would be baked into it.
  const idRef = useRef<string | null>(conversationId);
  const getConversationId = useCallback(() => (idRef.current ??= crypto.randomUUID()), []);
  const [modelId, setModelId] = useState<string | null>(null);
  const isNew = conversationId === null;

  const onTurnEnd = useCallback(
    ({ failed }: { failed: boolean }) => {
      notifyConversationsChanged();
      // A brand-new chat gets its own URL after the first answer, so reload/bookmark works.
      // Not after an error: the move remounts this view, and an error that produced no text
      // isn't saved, so the banner (and its hint or Try again) would vanish. The next
      // successful answer moves it instead.
      if (isNew && idRef.current && !failed) router.replace(`/chat/${idRef.current}`);
    },
    [isNew, router],
  );

  const { messages, isStreaming, send, stop } = useChatStream({ getConversationId, initialMessages, onTurnEnd });

  const lastQuestion = messages.findLast((m) => m.role === "user")?.content;
  const retry = () => lastQuestion && send(lastQuestion, modelId, { retry: true });

  return (
    <MotionConfig reducedMotion="user">
      <PageHeader title={title}>
        <ModelSwitcher value={modelId} onChange={setModelId} disabled={isStreaming} />
      </PageHeader>
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
        <div className="flex-1 py-6">
          {messages.length === 0 ? (
            <EmptyState onPick={(text) => send(text, modelId)} />
          ) : (
            <MessageList messages={messages} onRetry={retry} />
          )}
        </div>
        <div className="sticky bottom-0 bg-gradient-to-t from-background from-70% pt-2 pb-4">
          <Composer isStreaming={isStreaming} disabled={modelId === null} onSend={(text) => send(text, modelId)} onStop={stop} />
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Atlas can make mistakes. Answers aren&apos;t based on company documents yet.
          </p>
        </div>
      </div>
    </MotionConfig>
  );
}
