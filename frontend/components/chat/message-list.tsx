"use client";

import * as React from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { useChatStore } from "@/store/chat.store";
import { UserMessage } from "@/components/chat/user-message";
import { AssistantMessage } from "@/components/chat/assistant-message";
import { cn } from "@/lib/utils";
import type { Citation, Message } from "@/types/conversation";

export interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  onRetry: (lastUserContent: string) => void;
  className?: string;
}

function extractCitations(message: Message): Citation[] {
  const c = message.citations;
  if (!c || !Array.isArray((c as { sources?: unknown }).sources)) {
    return [];
  }
  return (c as { sources: Citation[] }).sources;
}

/**
 * Scrollable transcript: renders user/assistant bubbles, an in-flight
 * streaming assistant message, an error banner, and keeps the view pinned to
 * the newest content (auto-scroll on new messages / stream deltas).
 */
export function MessageList({
  messages,
  isLoading,
  onRetry,
  className,
}: MessageListProps) {
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const streamingText = useChatStore((s) => s.streamingText);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamError = useChatStore((s) => s.streamError);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages.length, streamingText, isStreaming]);

  const lastAssistantIndex = messages.reduce(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1,
  );
  const lastUserContent =
    [...messages].reverse().find((m) => m.role === "user")?.content ?? "";

  return (
    <div
      className={cn(
        "flex-1 overflow-y-auto px-3 py-4 sm:px-6",
        className,
      )}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-5">
        {isLoading && messages.length === 0 && (
          <div className="flex justify-center py-10">
            <Spinner size={28} aria-label="Loading messages" />
          </div>
        )}

        {messages.map((message, i) => {
          const citations = extractCitations(message);
          if (message.role === "user") {
            return <UserMessage key={message.id} message={message} />;
          }
          return (
            <AssistantMessage
              key={message.id}
              content={message.content}
              createdAt={message.created_at}
              citations={citations}
              tokenCount={message.token_count}
              costUsd={message.cost_usd}
              modelName={message.model_name}
              modelProvider={message.model_provider}
              canRetry={
                !isStreaming && i === lastAssistantIndex && Boolean(lastUserContent)
              }
              onRetry={
                i === lastAssistantIndex && Boolean(lastUserContent)
                  ? () => onRetry(lastUserContent)
                  : undefined
              }
            />
          );
        })}

        {isStreaming && (
          <AssistantMessage content={streamingText} isStreaming />
        )}

        {streamError && (
          <Alert variant="destructive">
            <AlertDescription>{streamError}</AlertDescription>
          </Alert>
        )}

        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </div>
  );
}

export default MessageList;
