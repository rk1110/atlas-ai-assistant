import { ChatView } from "@/components/chat/chat-view";

/** "/" = a new, empty chat. The conversation id is generated in the browser on first send. */
export default function NewChatPage() {
  return <ChatView conversationId={null} title="New chat" initialMessages={[]} />;
}
