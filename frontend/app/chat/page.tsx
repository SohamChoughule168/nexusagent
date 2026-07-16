import { ChatPage } from "@/features/chat/components/chat-page";

export const metadata = {
  title: "Chat",
};

/** Chat module entry route. */
export default function ChatPageRoute() {
  return <ChatPage />;
}
