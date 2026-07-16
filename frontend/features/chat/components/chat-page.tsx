"use client";

import * as React from "react";
import { MessageSquare, Plus } from "lucide-react";
import { useConversations } from "@/hooks/use-conversations";
import { useAgents } from "@/hooks/use-agents";
import { useChatStore } from "@/store/chat.store";
import { ConversationList } from "@/components/chat/conversation-list";
import { ChatThread } from "@/components/chat/chat-thread";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ConversationCreatePayload } from "@/types/conversation";

function makeSessionId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return crypto.randomUUID();
    }
  } catch {
    // fall through
  }
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Chat module root. Two-pane on desktop (conversation list + thread),
 * single-pane with a mobile back button on small screens. Server state
 * (conversations / agents) comes from React Query; the open conversation
 * and streaming state live in the Zustand chat store.
 */
export function ChatPage() {
  const {
    conversations,
    createConversationAsync,
    renameConversationAsync,
    deleteConversationAsync,
    isCreating,
  } = useConversations();
  const { agents, isLoading: isLoadingAgents } = useAgents();

  const selectedId = useChatStore((s) => s.selectedConversationId);
  const select = useChatStore((s) => s.selectConversation);

  const [mobileView, setMobileView] = React.useState<"list" | "thread">(
    "list",
  );
  const [newOpen, setNewOpen] = React.useState(false);

  // Auto-select the first conversation once the list loads.
  React.useEffect(() => {
    if (!selectedId && conversations.length > 0) {
      select(conversations[0].id);
    }
  }, [conversations, selectedId, select]);

  const agentById = React.useMemo(() => {
    const map = new Map<string, (typeof agents)[number]>();
    for (const a of agents) map.set(a.id, a);
    return map;
  }, [agents]);

  const selected = React.useMemo(
    () => conversations.find((c) => c.id === selectedId) ?? null,
    [conversations, selectedId],
  );

  const handleSelect = React.useCallback(
    (id: string) => {
      select(id);
      setMobileView("thread");
    },
    [select],
  );

  const handleCreate = React.useCallback(
    async (agentId: string, name?: string) => {
      const payload: ConversationCreatePayload = {
        agent_id: agentId,
        session_id: makeSessionId(),
        user_identifier: null,
        user_metadata: null,
        status: "active",
      };
      const created = await createConversationAsync(payload);
      select(created.id);
      setMobileView("thread");
      // Best-effort: a name maps onto the conversation `summary`.
      if (name) {
        try {
          await renameConversationAsync({ id: created.id, payload: { summary: name } });
        } catch {
          // name is optional; ignore rename failures
        }
      }
    },
    [createConversationAsync, select],
  );

  const handleRename = React.useCallback(
    async (id: string, name: string) => {
      await renameConversationAsync({ id, payload: { summary: name } });
    },
    [renameConversationAsync],
  );

  const handleDelete = React.useCallback(
    async (id: string) => {
      await deleteConversationAsync(id);
      if (id === selectedId) {
        select(null); // auto-select effect picks the next remaining
        setMobileView("list");
      }
    },
    [deleteConversationAsync, selectedId, select],
  );

  return (
    <div className="flex h-full min-h-0 overflow-hidden rounded-xl border bg-card">
      <div
        className={cn(
          "w-full md:w-72 md:shrink-0 md:border-r md:flex",
          mobileView === "list" ? "flex" : "hidden",
        )}
      >
        <ConversationList
          className="w-full"
          conversations={conversations}
          agents={agents}
          isLoadingAgents={isLoadingAgents}
          selectedId={selectedId}
          newOpen={newOpen}
          onNewOpenChange={setNewOpen}
          onSelect={handleSelect}
          onCreate={handleCreate}
          onRename={handleRename}
          onDelete={handleDelete}
          isCreating={isCreating}
        />
      </div>

      <div
        className={cn(
          "min-w-0 flex-1 md:flex",
          mobileView === "thread" ? "flex" : "hidden",
        )}
      >
        {selected ? (
          <ChatThread
            conversation={selected}
            agent={agentById.get(selected.agent_id)}
            onBack={() => setMobileView("list")}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <MessageSquare className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium">No conversation selected</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Choose a conversation or start a new one.
              </p>
            </div>
            <Button onClick={() => setNewOpen(true)}>
              <Plus className="h-4 w-4" />
              New conversation
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatPage;
