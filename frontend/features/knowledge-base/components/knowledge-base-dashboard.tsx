"use client";

import * as React from "react";
import { BookOpen, Plus, Search, SearchX, TriangleAlert } from "lucide-react";
import { useKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useNotificationStore } from "@/store/notification.store";
import { getErrorMessage } from "@/lib/api-error";
import { KnowledgeBaseTable } from "@/features/knowledge-base/components/knowledge-base-table";
import { KnowledgeBaseFormDialog } from "@/features/knowledge-base/components/knowledge-base-form-dialog";
import { DeleteKnowledgeBaseDialog } from "@/features/knowledge-base/components/delete-knowledge-base-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { Tooltip } from "@/components/ui/tooltip";
import { LoadingState } from "@/components/ui/loading-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type {
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
} from "@/types/knowledge-base";

/**
 * Knowledge Base dashboard: list + search + create / edit / delete. Server
 * state (KB list) lives in React Query; transient UI (the form/search dialogs,
 * query string) is local component state. Success/error feedback is surfaced
 * through the notification store (toasts).
 */
export function KnowledgeBaseDashboard() {
  const {
    knowledgeBases,
    isLoading,
    isError,
    error,
    refetch,
    createKnowledgeBaseAsync,
    updateKnowledgeBaseAsync,
    isCreating,
    isUpdating,
    deleteKnowledgeBaseAsync,
    isDeleting,
  } = useKnowledgeBases();

  const notify = useNotificationStore();

  const [query, setQuery] = React.useState("");
  const [formOpen, setFormOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<KnowledgeBase | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<KnowledgeBase | null>(null);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return knowledgeBases;
    return knowledgeBases.filter(
      (kb) =>
        kb.name.toLowerCase().includes(q) ||
        (kb.description ?? "").toLowerCase().includes(q),
    );
  }, [knowledgeBases, query]);

  const openCreate = () => {
    setEditTarget(null);
    setFormOpen(true);
  };

  const openEdit = (kb: KnowledgeBase) => {
    setEditTarget(kb);
    setFormOpen(true);
  };

  const handleSubmit = async (payload: KnowledgeBaseCreatePayload) => {
    try {
      if (editTarget) {
        await updateKnowledgeBaseAsync({ id: editTarget.id, payload });
        notify.success("Knowledge base updated", payload.name);
      } else {
        await createKnowledgeBaseAsync(payload);
        notify.success("Knowledge base created", payload.name);
      }
      setFormOpen(false);
      setEditTarget(null);
    } catch (err) {
      notify.error("Could not save knowledge base", getErrorMessage(err));
    }
  };

  const handleDeleteConfirm = async (id: string) => {
    try {
      await deleteKnowledgeBaseAsync(id);
      notify.success("Knowledge base deleted");
      setDeleteTarget(null);
    } catch (err) {
      notify.error("Could not delete knowledge base", getErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Knowledge Bases
          </h1>
          <p className="text-sm text-muted-foreground">
            Manage documents and retrieval sources for your agents.
          </p>
        </div>
        <Tooltip content="Create a new knowledge base">
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" />
            New knowledge base
          </Button>
        </Tooltip>
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search knowledge bases..."
          aria-label="Search knowledge bases"
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <LoadingState label="Loading knowledge bases..." className="py-16" />
      ) : isError ? (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertTitle>Failed to load knowledge bases</AlertTitle>
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
      ) : knowledgeBases.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-8 w-8" />}
          title="No knowledge bases yet"
          description="Create a knowledge base to start uploading and indexing documents for retrieval."
          action={
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              New knowledge base
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<SearchX className="h-8 w-8" />}
          title="No matches"
          description={`No knowledge bases match “${query}”.`}
        />
      ) : (
        <KnowledgeBaseTable
          knowledgeBases={filtered}
          onEdit={openEdit}
          onDelete={setDeleteTarget}
        />
      )}

      <KnowledgeBaseFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editTarget}
        onSubmit={handleSubmit}
        isSubmitting={isCreating || isUpdating}
      />

      <DeleteKnowledgeBaseDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        knowledgeBase={deleteTarget}
        onConfirm={handleDeleteConfirm}
        isDeleting={isDeleting}
      />
    </div>
  );
}

export default KnowledgeBaseDashboard;
