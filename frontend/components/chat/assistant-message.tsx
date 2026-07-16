import { Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTimestamp } from "@/lib/datetime";
import { Markdown } from "@/components/chat/markdown";
import { Citations } from "@/components/chat/citations";
import { TokenUsage } from "@/components/chat/token-usage";
import { MessageActions } from "@/components/chat/message-actions";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import type { Citation } from "@/types/conversation";

export interface AssistantMessageProps {
  content: string;
  createdAt?: string | null;
  citations?: Citation[] | null;
  tokenCount?: number | null;
  costUsd?: number | null;
  modelName?: string | null;
  modelProvider?: string | null;
  /** True for the live, in-flight synthetic message. */
  isStreaming?: boolean;
  canRetry?: boolean;
  onRetry?: () => void;
  className?: string;
}

/** Left-aligned assistant message: avatar, markdown, citations, footer meta. */
export function AssistantMessage({
  content,
  createdAt,
  citations,
  tokenCount,
  costUsd,
  modelName,
  modelProvider,
  isStreaming = false,
  canRetry = false,
  onRetry,
  className,
}: AssistantMessageProps) {
  const showTyping = isStreaming && !content;
  const showCitations = !isStreaming && citations && citations.length > 0;

  return (
    <div className={cn("flex justify-start", className)}>
      <div className="flex w-full max-w-[85%] gap-3 sm:max-w-[80%]">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="rounded-2xl rounded-bl-sm border bg-card px-4 py-2.5 text-sm text-card-foreground shadow-sm">
            {showTyping ? (
              <TypingIndicator />
            ) : (
              <Markdown content={content} />
            )}
            {showCitations && <Citations citations={citations as Citation[]} />}
          </div>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <TokenUsage
              tokenCount={tokenCount}
              costUsd={costUsd}
              modelName={modelName}
              modelProvider={modelProvider}
              compact
            />
            {createdAt && (
              <span className="text-[11px] text-muted-foreground">
                {formatTimestamp(createdAt)}
              </span>
            )}
            {!isStreaming && (
              <MessageActions
                content={content}
                canRetry={canRetry}
                onRetry={onRetry}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AssistantMessage;
