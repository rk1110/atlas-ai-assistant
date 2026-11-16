import { notFound } from "next/navigation";
import { connection } from "next/server";

import { ChatView } from "@/components/chat/chat-view";
import { api, ApiError } from "@/lib/api";
import { toChatMessage } from "@/lib/messages";

/**
 * An existing conversation. A Server Component: it fetches the history on the server (inside
 * Docker, from http://backend:8000), so the page arrives with messages already rendered.
 */
export default async function ConversationPage({ params }: PageProps<"/chat/[id]">) {
  const { id } = await params; // Next.js 16: params is a Promise
  // A conversation is per-request data: render it at request time, never prerender it.
  // (Without this, Next.js flags the fetches below as unstable values during prerender.)
  await connection();
  const data = await load(id);
  if (data === null) notFound();
  const title = data.conversations.find((c) => c.id === id)?.title ?? "Conversation";
  return <ChatView key={id} conversationId={id} title={title} initialMessages={data.messages.map(toChatMessage)} />;
}

/** Fetch history + titles. null = no such conversation (404) or not a valid id (422). */
async function load(id: string) {
  try {
    const [messages, conversations] = await Promise.all([api.messages(id), api.conversations()]);
    return { messages, conversations };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return null;
    throw error; // anything else (backend down) is shown by app/chat/error.tsx
  }
}
