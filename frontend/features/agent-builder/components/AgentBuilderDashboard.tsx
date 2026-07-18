"use client";

import * as React from "react";
import { Boxes, Plus, Search, SearchX, TriangleAlert } from "lucide-react";

import { useAgents, useCreateAgent, useUpdateAgent, useDeleteAgent, useDuplicateAgent } from "../hooks/use-agents";
import { useNotificationStore } from "@/store/notification.store";
import { getErrorMessage } from "@/lib/api-error";
import type { AgentDetail } from "../types";
import type { AgentCreatePayload, AgentUpdatePayload } from "../types";
import { AgentList } from "./AgentList";
import { AgentBuilderFormDialog } from "./AgentBuilderFormDialog";
import { AgentDetailDialog } from "./AgentDetailDialog";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { Tooltip } from "@/components/ui/tooltip";
import { LoadingState } from "@/components/ui/loading-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Agent Builder dashboard: list + search + create / edit / view / duplicate /
 * delete. Server state (the agent list) lives in React Query; transient UI
 * (search string, the form/view/delete dialogs, and their targets) is local
 * component state. Success/error feedback is surfaced through the notification
 * store (toasts), and the form dialog shows its own inline submit error.
 */
export function AgentBuilderDashboard() {
  const {
    data: agents,
    isLoading,
    isError,
    error,
    refetch,
  } = useAgents();

  const createMutation = useCreateAgent();
  const updateMutation = useUpdateAgent();
  const deleteMutation = useDeleteAgent();
  const duplicateMutation = useDuplicateAgent();

  const notify = useNotificationStore();

  const [query, setQuery] = React.useState("");
  const [formOpen, setFormOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<AgentDetail | null>(null);
  const [viewTarget, setViewTarget] = React.useState<AgentDetail | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<AgentDetail | null>(
    null,
  );

  const filtered = React.useMemo(() => {
    const list = agents ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.description?.toLowerCase().includes(q) ?? false),
    );
  }, [agents, query]);

  const openCreate = () => {
    setEditTarget(null);
    setFormOpen(true);
  };

  const openEdit = (agent: AgentDetail) => {
    setEditTarget(agent);
    setFormOpen(true);
  };

  const handleFormSubmit = async (
    payload: AgentCreatePayload | AgentUpdatePayload,
  ) => {
    try {
      if (editTarget) {
        await updateMutation.mutateAsync({
          id: editTarget.id,
          payload: payload as AgentUpdatePayload,
        });
        notify.success("Agent updated", payload.name);
      } else {
        await createMutation.mutateAsync(payload as AgentCreatePayload);
        notify.success("Agent created", payload.name);
      }
      setFormOpen(false);
      setEditTarget(null);
    } catch (err) {
      // Re-throw so the form dialog can render the inline error state.
      throw err;
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMutation.mutateAsync(deleteTarget.id);
      notify.success("Agent deleted", deleteTarget.name);
      setDeleteTarget(null);
    } catch (err) {
      notify.error("Could not delete agent", getErrorMessage(err));
    }
  };

  const handleDuplicate = async (agent: AgentDetail) => {
    try {
      await duplicateMutation.mutateAsync({ id: agent.id });
      notify.success("Agent duplicated", agent.name);
    } catch (err) {
      notify.error("Could not duplicate agent", getErrorMessage(err));
    }
  };

  const isFormSubmitting =
    createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Agent Builder
          </h1>
          <p className="text-sm text-muted-foreground">
            Compose and configure autonomous agents.
          </p>
        </div>
        <Tooltip content="Create a new autonomous agent">
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" />
            New agent
          </Button>
        </Tooltip>
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search agents..."
          aria-label="Search agents"
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <LoadingState label="Loading agents..." className="py-16" />
      ) : isError ? (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertTitle>Failed to load agents</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-4">
            <span>{getErrorMessage(error)}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="shrink-0"
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : (agents?.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Boxes className="h-8 w-8" />}
          title="No agents yet"
          description="Create your first agent to start automating conversations."
          action={
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              New agent
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<SearchX className="h-8 w-8" />}
          title="No matches"
          description={`No agents match “${query}”.`}
        />
      ) : (
        <AgentList
          agents={filtered}
          onEdit={openEdit}
          onView={setViewTarget}
          onDelete={setDeleteTarget}
          onDuplicate={handleDuplicate}
        />
      )}

      <AgentBuilderFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editTarget}
        onSubmit={handleFormSubmit}
        isSubmitting={isFormSubmitting}
      />

      <AgentDetailDialog
        open={Boolean(viewTarget)}
        onOpenChange={(o) => !o && setViewTarget(null)}
        agent={viewTarget}
        onEdit={() => viewTarget && openEdit(viewTarget)}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete Agent"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmText={deleteMutation.isPending ? "Deleting..." : "Delete"}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}

export default AgentBuilderDashboard;
