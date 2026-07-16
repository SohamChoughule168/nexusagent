"use client";

import * as React from "react";
import { MessageSquare, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Modal } from "@/components/ui/modal";
import { EmptyState } from "@/components/ui/empty-state";
import { ConversationItem } from "@/components/chat/conversation-item";
import { NewConversationDialog } from "@/components/chat/new-conversation-dialog";
import { conversationTitle } from "@/types/conversation";
import type { Agent, Conversation } from "@/types/conversation";

export interface ConversationListProps {
  conversations: Conversation[];
  agents: Agent[];
  isLoadingAgents: boolean;
  selectedId: string | null;
  newOpen: boolean;
  onNewOpenChange: (open: boolean) => void;
  onSelect: (id: string) => void;
  onCreate: (agentId: string, name?: string) => void | Promise<void>;
  onRename: (id: string, name: string) => void | Promise<void>;
  onDelete: (id: string) => void | Promise<void>;
  isCreating?: boolean;
  className?: string;
}

/**
 * Left pane: conversation list + create / rename / delete controls. Owns the
 * new-chat, rename and delete-confirmation dialogs; the actual mutations
 * are delegated to the callbacks (which live in the page / React Query).
 */
export function ConversationList({
  conversations,
  agents,
  isLoadingAgents,
  selectedId,
  newOpen,
  onNewOpenChange,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  isCreating = false,
  className,
}: ConversationListProps) {
  const [renameTarget, setRenameTarget] = React.useState<Conversation | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const [deleteTarget, setDeleteTarget] = React.useState<Conversation | null>(null);
  const [busy, setBusy] = React.useState(false);

  const agentById = React.useMemo(() => {
    const map = new Map<string, Agent>();
    for (const a of agents) map.set(a.id, a);
    return map;
  }, [agents]);

  const openRename = (c: Conversation) => {
    setRenameTarget(c);
    setRenameValue(conversationTitle(c, ""));
  };

  const confirmRename = async () => {
    if (!renameTarget) return;
    setBusy(true);
    try {
      await onRename(renameTarget.id, renameValue.trim());
      setRenameTarget(null);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await onDelete(deleteTarget.id);
      setDeleteTarget(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b px-3 py-3">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <Button
            size="sm"
            onClick={() => onNewOpenChange(true)}
            aria-label="New chat"
          >
            <Plus className="h-4 w-4" />
            New
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <EmptyState
              icon={<MessageSquare className="h-8 w-8" />}
              title="No conversations yet"
              description="Start a new chat with one of your agents."
              action={
                <Button onClick={() => onNewOpenChange(true)}>
                  <Plus className="h-4 w-4" />
                  New conversation
                </Button>
              }
              className="mt-6"
            />
          ) : (
            <div className="space-y-1">
              {conversations.map((c) => (
                <ConversationItem
                  key={c.id}
                  conversation={c}
                  agent={agentById.get(c.agent_id)}
                  isActive={c.id === selectedId}
                  onSelect={() => onSelect(c.id)}
                  onRename={() => openRename(c)}
                  onDelete={() => setDeleteTarget(c)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <NewConversationDialog
        open={newOpen}
        onOpenChange={onNewOpenChange}
        agents={agents}
        isLoadingAgents={isLoadingAgents}
        isCreating={isCreating}
        onCreate={(agentId, name) => {
          onNewOpenChange(false);
          void onCreate(agentId, name);
        }}
      />

      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(o) => !o && setRenameTarget(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
            <DialogDescription>Give this conversation a memorable name.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label htmlFor="rename-input">Name</Label>
            <Input
              id="rename-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="Conversation name"
              disabled={busy}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameTarget(null)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button onClick={confirmRename} disabled={busy || !renameValue.trim()}>
              <Pencil className="h-4 w-4" />
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Delete conversation?"
        description="This permanently removes the conversation and its messages. This cannot be undone."
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={busy}
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">
          {deleteTarget ? conversationTitle(deleteTarget, "this conversation") : ""}
        </p>
      </Modal>
    </div>
  );
}

export default ConversationList;
