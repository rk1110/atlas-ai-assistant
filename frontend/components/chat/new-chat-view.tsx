"use client";

import { useRouter } from "next/navigation";

import { ChatView } from "@/components/chat/chat-view";

/**
 * The "New chat" page's view. Next.js 16 (cacheComponents) doesn't unmount a page on
 * navigation: it hides it with React's <Activity> and restores it, state included. Without a
 * reset, "New chat" would come back holding the previous chat's messages and conversation id.
 *
 * `bfcacheId` changes on every fresh navigation (Link click, push, replace) but not on browser
 * back/forward, so keying on it starts a fresh chat each time while Back still restores.
 */
export function NewChatView() {
  const { bfcacheId } = useRouter();
  return <ChatView key={bfcacheId} conversationId={null} title="New chat" initialMessages={[]} />;
}
