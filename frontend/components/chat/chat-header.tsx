"use client";

import { ArrowLeft, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TokenUsage } from "@/components/chat/token-usage";
import { cn } from "@/lib/utils";
import type { Agent, Conversation } from "@/types/conversation";

export interface ChatHeaderProps {
  title: string;
  agent?: Agent | undefined;
  conversation?: Conversation | undefined;
  /** Mobile-only back-to-list control. */
  onBack?: () => void;
  className?: string;
}

/** Thread header: conversation title, agent identity, and total token usage. */
export function ChatHeader({
  title,
  agent,
  conversation,
  onBack,
  className,
}: ChatHeaderProps) {
  const subtitle = agent
    ? `${agent.name}${agent.model_name ? ` · ${agent.model_name}` : ""}`
    : "Agent";

  const showTotals =
    conversation &&
    (conversation.total_tokens > 0 || conversation.total_cost_usd > 0);

  return (
    <header
      className={cn(
        "flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-background px-3 sm:px-4",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {onBack && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onBack}
            aria-label="Back to conversations"
            className="md:hidden"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
        )}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium leading-tight">
            {title}
          </p>
          <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
        </div>
      </div>

      {showTotals && (
        <TokenUsage
          tokenCount={conversation.total_tokens}
          costUsd={conversation.total_cost_usd}
          compact
          className="shrink-0"
        />
      )}
    </header>
  );
}

export default ChatHeader;
