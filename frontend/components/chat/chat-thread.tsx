"use client";

import * as React from "react";
import { useMessages } from "@/hooks/use-messages";
import { useChatStream } from "@/hooks/use-chat-stream";
import { useChatStore } from "@/store/chat.store";
import { ChatHeader } from "@/components/chat/chat-header";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationStarters } from "@/components/chat/conversation-starters";
import { conversationTitle } from "@/types/conversation";
import type { Agent, Conversation, Message } from "@/types/conversation";

export interface ChatThreadProps {
  conversation: Conversation;
  agent?: Agent | undefined;
  /** Mobile-only back control. */
  onBack?: () => void;
  /** Optional starter prompts shown when the conversation is empty (demo). */
  starters?: string[];
}

function makeMessageId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return `temp-${crypto.randomUUID()}`;
    }
  } catch {
    // fall through
  }
  return `temp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * A single open conversation: header + transcript + composer. Owns the send
 * flow — optimistic user message, then streams the assistant reply via
 * useChatStream, then invalidates the messages query to pick up the
 * persisted (citations / tokens) messages.
 */
export function ChatThread({
  conversation,
  agent,
  onBack,
  starters,
}: ChatThreadProps) {
  const {
    messages,
    isLoading,
    invalidate,
    appendOptimistic,
  } = useMessages(conversation.id);
  const { send, stop, isStreaming } = useChatStream();
  const resetStreaming = useChatStore((s) => s.resetStreaming);

  React.useEffect(() => {
    return () => resetStreaming();
  }, [resetStreaming]);

  const handleSend = React.useCallback(
    async (text: string) => {
      const userMsg: Message = {
        id: makeMessageId(),
        conversation_id: conversation.id,
        organization_id: "",
        role: "user",
        content: text,
        token_count: text.split(/\s+/).filter(Boolean).length,
        citations: null,
        tool_calls: null,
        tool_results: null,
        model_provider: null,
        model_name: null,
        cost_usd: 0,
        created_at: new Date().toISOString(),
      };
      appendOptimistic(userMsg);
      await send(conversation.id, text, { onDone: () => invalidate() });
    },
    [conversation.id, appendOptimistic, send, invalidate],
  );

  const handleRetry = React.useCallback(
    (lastUserContent: string) => {
      void handleSend(lastUserContent);
    },
    [handleSend],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader
        title={conversationTitle(conversation, "New conversation")}
        agent={agent}
        conversation={conversation}
        onBack={onBack}
      />
      <MessageList
        messages={messages}
        isLoading={isLoading}
        onRetry={handleRetry}
        className="min-h-0"
      />
      {starters && (messages?.length ?? 0) === 0 && (
        <ConversationStarters starters={starters} />
      )}
      <ChatInput
        onSend={handleSend}
        onStop={stop}
        isStreaming={isStreaming}
      />
    </div>
  );
}

export default ChatThread;
