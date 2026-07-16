"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { knowledgeBaseService } from "@/services/knowledge-base.service";
import { useDocuments } from "@/hooks/use-documents";
import { useKnowledgeBases, knowledgeBaseKeys } from "@/hooks/use-knowledge-bases";
import { useNotificationStore } from "@/store/notification.store";
import { getErrorMessage } from "@/lib/api-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { KnowledgeBaseFormDialog } from "@/features/knowledge-base/components/knowledge-base-form-dialog";
import { DeleteKnowledgeBaseDialog } from "@/features/knowledge-base/components/delete-knowledge-base-dialog";
import { DocumentUpload } from "@/features/knowledge-base/components/document-upload";
import { DocumentList } from "@/features/knowledge-base/components/document-list";
import { DocumentMetadataDialog } from "@/features/knowledge-base/components/document-metadata-dialog";
import { DeleteDocumentDialog } from "@/features/knowledge-base/components/delete-document-dialog";
import type {
  Document,
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
} from "@/types/knowledge-base";

export interface KnowledgeBaseDetailProps {
  kbId: string;
}

/**
 * Knowledge base detail screen: header (with edit / delete), document upload,
 * and the document list with processing + pagination. Server state comes from
 * React Query (KB detail + documents); transient UI (dialogs, the document
 * currently being processed) is local state.
 */
export function KnowledgeBaseDetail({ kbId }: KnowledgeBaseDetailProps) {
  const {
    documents,
    isLoading: docsLoading,
    isError: docsError,
    error: docsErrorObj,
    refetch: refetchDocs,
    processDocument,
    deleteDocumentAsync,
    isDeleting: isDeletingDoc,
  } = useDocuments(kbId);

  const {
    updateKnowledgeBaseAsync,
    isUpdating,
    deleteKnowledgeBaseAsync,
    isDeleting,
  } = useKnowledgeBases();

  const notify = useNotificationStore();

  const kbQuery = useQuery({
    queryKey: knowledgeBaseKeys.detail(kbId),
    queryFn: () => knowledgeBaseService.getKnowledgeBase(kbId),
  });

  const [editOpen, setEditOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [processingId, setProcessingId] = React.useState<string | null>(null);
  const [metaDoc, setMetaDoc] = React.useState<Document | null>(null);
  const [deleteDoc, setDeleteDoc] = React.useState<Document | null>(null);

  const kb = kbQuery.data ?? null;

  const handleEditSubmit = async (payload: KnowledgeBaseCreatePayload) => {
    try {
      await updateKnowledgeBaseAsync({ id: kbId, payload });
      notify.success("Knowledge base updated", payload.name);
      setEditOpen(false);
      // Refresh the detail header with the new config.
      await kbQuery.refetch();
    } catch (err) {
      notify.error("Could not update knowledge base", getErrorMessage(err));
    }
  };

  const handleDeleteKb = async (id: string) => {
    try {
      await deleteKnowledgeBaseAsync(id);
      notify.success("Knowledge base deleted");
      setDeleteOpen(false);
    } catch (err) {
      notify.error("Could not delete knowledge base", getErrorMessage(err));
    }
  };

  const handleProcess = async (id: string) => {
    setProcessingId(id);
    try {
      await processDocument(id);
      notify.success("Document processed", "Extracted, chunked and indexed.");
    } catch (err) {
      notify.error("Processing failed", getErrorMessage(err));
    } finally {
      setProcessingId(null);
    }
  };

  const handleDeleteDoc = async (id: string) => {
    try {
      await deleteDocumentAsync(id);
      notify.success("Document deleted");
      setDeleteDoc(null);
    } catch (err) {
      notify.error("Could not delete document", getErrorMessage(err));
    }
  };

  if (kbQuery.isLoading) {
    return <LoadingState label="Loading knowledge base..." className="py-20" />;
  }

  if (kbQuery.isError) {
    return (
      <Alert variant="destructive">
        <TriangleAlert className="h-4 w-4" />
        <AlertTitle>Knowledge base not found</AlertTitle>
        <AlertDescription className="flex items-center justify-between gap-4">
          <span>{getErrorMessage(kbQuery.error)}</span>
          <Button asChild variant="outline" size="sm" className="shrink-0">
            <Link href="/knowledge-bases">Back to list</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link
            href="/knowledge-bases"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Knowledge Bases
          </Link>
          <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight">
            {kb?.name}
          </h1>
          {kb?.description && (
            <p className="mt-1 text-sm text-muted-foreground">{kb.description}</p>
          )}
          {kb && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="outline" className="capitalize">
                {kb.embedding_model}
              </Badge>
              <Badge variant="secondary" className="capitalize">
                {kb.chunk_strategy}
              </Badge>
              <Badge variant="outline">{kb.chunk_size} tok / chunk</Badge>
              <Badge variant="outline">{kb.chunk_overlap} overlap</Badge>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDeleteOpen(true)}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetchDocs()}
            aria-label="Refresh documents"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Upload documents</h2>
        <DocumentUpload knowledgeBaseId={kbId} />
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">
            Documents
            {documents.length > 0 && (
              <span className="ml-2 text-muted-foreground">
                ({documents.length})
              </span>
            )}
          </h2>
        </div>
        <DocumentList
          documents={documents}
          isLoading={docsLoading}
          isError={docsError}
          error={docsErrorObj}
          refetch={refetchDocs}
          processingId={processingId}
          onProcess={handleProcess}
          onViewMetadata={setMetaDoc}
          onDelete={setDeleteDoc}
        />
      </section>

      <KnowledgeBaseFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initial={kb}
        onSubmit={handleEditSubmit}
        isSubmitting={isUpdating}
      />

      <DeleteKnowledgeBaseDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        knowledgeBase={kb}
        onConfirm={handleDeleteKb}
        isDeleting={isDeleting}
      />

      <DocumentMetadataDialog
        open={Boolean(metaDoc)}
        onOpenChange={(o) => !o && setMetaDoc(null)}
        document={metaDoc}
      />

      <DeleteDocumentDialog
        open={Boolean(deleteDoc)}
        onOpenChange={(o) => !o && setDeleteDoc(null)}
        document={deleteDoc}
        onConfirm={handleDeleteDoc}
        isDeleting={isDeletingDoc}
      />
    </div>
  );
}

export default KnowledgeBaseDetail;
