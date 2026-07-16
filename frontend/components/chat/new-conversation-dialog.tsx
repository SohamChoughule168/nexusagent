"use client";

import * as React from "react";
import { Bot, Loader2, Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types/conversation";

export interface NewConversationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[];
  isLoadingAgents: boolean;
  isCreating: boolean;
  onCreate: (agentId: string, name?: string) => void;
}

/**
 * "New chat" flow: pick an agent (the backend requires an `agent_id` to
 * create a conversation) and optionally name it. The name maps onto the
 * conversation `summary` field (its display title).
 */
export function NewConversationDialog({
  open,
  onOpenChange,
  agents,
  isLoadingAgents,
  isCreating,
  onCreate,
}: NewConversationDialogProps) {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [name, setName] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setSelectedId(null);
      setName("");
    }
  }, [open]);

  const confirm = () => {
    if (!selectedId) return;
    onCreate(selectedId, name.trim() || undefined);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New conversation</DialogTitle>
          <DialogDescription>
            Choose an agent to chat with. Optionally give the conversation a name.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label>Agent</Label>
            {isLoadingAgents ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Spinner size={18} aria-label="Loading agents" />
                Loading agents…
              </div>
            ) : agents.length === 0 ? (
              <p className="rounded-md border border-dashed px-3 py-4 text-sm text-muted-foreground">
                No agents available. Create one in the Agent Builder first.
              </p>
            ) : (
              <div className="max-h-60 space-y-2 overflow-y-auto">
                {agents.map((agent) => {
                  const active = agent.id === selectedId;
                  return (
                    <button
                      type="button"
                      key={agent.id}
                      onClick={() => setSelectedId(agent.id)}
                      aria-pressed={active}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                        active
                          ? "border-primary bg-primary/5 ring-1 ring-primary"
                          : "hover:bg-accent",
                      )}
                    >
                      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                        <Bot className="h-4 w-4" aria-hidden="true" />
                      </div>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {agent.name}
                        </span>
                        {agent.description && (
                          <span className="mt-0.5 block line-clamp-2 text-xs text-muted-foreground">
                            {agent.description}
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="conversation-name">Name (optional)</Label>
            <Input
              id="conversation-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Onboarding Q&A"
              disabled={isCreating}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isCreating}
          >
            Cancel
          </Button>
          <Button onClick={confirm} disabled={!selectedId || isCreating}>
            {isCreating && <Loader2 className="h-4 w-4 animate-spin" />}
            <Plus className="h-4 w-4" />
            Start chat
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default NewConversationDialog;
