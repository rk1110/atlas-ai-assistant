import { NewChatView } from "@/components/chat/new-chat-view";

/** "/" = a new, empty chat. The conversation id is generated in the browser on first send. */
export default function NewChatPage() {
  return <NewChatView />;
}
