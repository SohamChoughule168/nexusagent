"use client";

import * as React from "react";
import { MessageSquare, Pencil, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { conversationTitle } from "@/types/conversation";
import { formatTimeShort } from "@/lib/datetime";
import type { Agent, Conversation } from "@/types/conversation";

export interface ConversationItemProps {
  conversation: Conversation;
  agent?: Agent | undefined;
  isActive: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}

/** A single conversation row: title, agent/meta, hover rename + delete. */
export function ConversationItem({
  conversation,
  agent,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const title =
    conversationTitle(conversation, "") || agent?.name || "New conversation";
  const stamp = conversation.updated_at ?? conversation.created_at;
  const meta = agent?.name ?? "Agent";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-md px-3 py-2 transition-colors",
        isActive
          ? "bg-primary/10 text-foreground"
          : "text-foreground/90 hover:bg-accent",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={isActive ? "true" : undefined}
        className="flex min-w-0 flex-1 items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <MessageSquare
          className={cn(
            "h-4 w-4 shrink-0",
            isActive ? "text-primary" : "text-muted-foreground",
          )}
          aria-hidden="true"
        />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium">{title}</span>
          <span className="truncate text-xs text-muted-foreground">
            {meta} · {conversation.message_count}{" "}
            {conversation.message_count === 1 ? "msg" : "msgs"}
            {stamp ? ` · ${formatTimeShort(stamp)}` : ""}
          </span>
        </span>
      </button>

      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          onClick={onRename}
          aria-label="Rename conversation"
          className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete conversation"
          className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export default ConversationItem;
