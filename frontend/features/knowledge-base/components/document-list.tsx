"use client";

import * as React from "react";
import { Eye, FileText, Layers, Loader2, RefreshCw, Trash2, TriangleAlert } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingState } from "@/components/ui/loading-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Pagination } from "@/components/ui/pagination";
import { DocumentStatusBadge } from "@/features/knowledge-base/components/document-status-badge";
import { formatFileSize } from "@/types/knowledge-base";
import { formatTimestamp } from "@/lib/datetime";
import type { Document } from "@/types/knowledge-base";

const PAGE_SIZE = 8;

export interface DocumentListProps {
  documents: Document[];
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  refetch?: () => void;
  /** Id of the document currently being ingested/embedded (shows spinner). */
  processingId?: string | null;
  onProcess: (id: string) => void;
  onViewMetadata: (doc: Document) => void;
  onDelete: (doc: Document) => void;
}

/**
 * Document table for a knowledge base: processing status, chunk count, upload
 * date, and per-row actions (process/index, view metadata, delete). Supports
 * client-side pagination and renders loading / error / empty states.
 */
export function DocumentList({
  documents,
  isLoading = false,
  isError = false,
  error,
  refetch,
  processingId,
  onProcess,
  onViewMetadata,
  onDelete,
}: DocumentListProps) {
  const [page, setPage] = React.useState(1);

  const pageCount = Math.max(1, Math.ceil(documents.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageDocs = documents.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  // Keep the page in range when the underlying list shrinks.
  React.useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  if (isLoading) {
    return <LoadingState label="Loading documents..." className="py-16" />;
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        <TriangleAlert className="h-4 w-4" />
        <AlertTitle>Failed to load documents</AlertTitle>
        <AlertDescription className="flex items-center justify-between gap-4">
          <span>{error instanceof Error ? error.message : "Something went wrong."}</span>
          {refetch && (
            <Button variant="outline" size="sm" onClick={refetch} className="shrink-0">
              Retry
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={<FileText className="h-8 w-8" />}
        title="No documents yet"
        description="Upload a PDF to start building this knowledge base's retrieval index."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden sm:table-cell">Size</TableHead>
              <TableHead className="hidden md:table-cell">Chunks</TableHead>
              <TableHead className="hidden lg:table-cell">Added</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageDocs.map((doc) => {
              const isProcessing = processingId === doc.id;
              const canProcess = doc.status === "uploaded" || doc.status === "failed";
              const canIndex = doc.status === "processed";
              return (
                <TableRow key={doc.id}>
                  <TableCell>
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {doc.title || doc.filename}
                      </p>
                      {doc.status === "failed" && doc.error_message ? (
                        <p
                          className="mt-0.5 flex items-center gap-1 truncate text-xs text-destructive"
                          title={doc.error_message}
                        >
                          <TriangleAlert className="h-3 w-3 shrink-0" />
                          {doc.error_message}
                        </p>
                      ) : (
                        <p className="truncate text-xs text-muted-foreground">
                          {doc.filename}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {isProcessing ? (
                      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Processing…
                      </span>
                    ) : (
                      <DocumentStatusBadge status={doc.status} />
                    )}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell text-muted-foreground">
                    {formatFileSize(doc.file_size)}
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-muted-foreground">
                    {doc.chunk_count ?? 0}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-muted-foreground">
                    {formatTimestamp(doc.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onViewMetadata(doc)}
                        aria-label={`View ${doc.title || doc.filename}`}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      {(canProcess || canIndex) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onProcess(doc.id)}
                          disabled={isProcessing}
                          aria-label={`Process ${doc.title || doc.filename}`}
                          title={canIndex ? "Embed & index" : "Extract, chunk & index"}
                        >
                          {canIndex ? (
                            <Layers className="h-4 w-4" />
                          ) : (
                            <RefreshCw className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onDelete(doc)}
                        aria-label={`Delete ${doc.title || doc.filename}`}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </div>
  );
}

export default DocumentList;
