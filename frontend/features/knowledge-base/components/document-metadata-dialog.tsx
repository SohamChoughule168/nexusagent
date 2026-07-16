"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { DocumentStatusBadge } from "@/features/knowledge-base/components/document-status-badge";
import { formatTimestamp } from "@/lib/datetime";
import {
  formatFileSize,
  type Document,
} from "@/types/knowledge-base";

export interface DocumentMetadataDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  document: Document | null;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b py-2 last:border-0">
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className="col-span-2 break-words text-sm">{children}</dd>
    </div>
  );
}

/**
 * Read-only viewer for a document's full metadata. Shows the processing state,
 * file details, chunk/page counts, error (if any) and the raw `metadata` blob.
 */
export function DocumentMetadataDialog({
  open,
  onOpenChange,
  document,
}: DocumentMetadataDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Document details</DialogTitle>
          <DialogDescription>
            {document?.title || document?.filename}
          </DialogDescription>
        </DialogHeader>

        {document && (
          <dl className="text-sm">
            <Field label="Status">
              <DocumentStatusBadge status={document.status} />
              {document.error_message && (
                <p className="mt-2 rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
                  {document.error_message}
                </p>
              )}
            </Field>
            <Field label="Title">{document.title || "—"}</Field>
            <Field label="Filename">{document.filename}</Field>
            <Field label="MIME type">{document.mime_type}</Field>
            <Field label="Size">{formatFileSize(document.file_size)}</Field>
            <Field label="Chunks">{document.chunk_count ?? 0}</Field>
            <Field label="Pages">{document.page_count ?? "—"}</Field>
            <Field label="Embedding ID">
              {document.embedding_id ?? "—"}
            </Field>
            <Field label="Uploaded">
              {formatTimestamp(document.created_at)}
            </Field>
            <Field label="Updated">
              {formatTimestamp(document.updated_at) || "—"}
            </Field>
            <Field label="Document ID">
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                {document.id}
              </code>
            </Field>
            <Field label="Metadata">
              <pre className="max-h-40 overflow-auto rounded-md bg-muted p-2 text-xs">
                {JSON.stringify(document.metadata ?? {}, null, 2)}
              </pre>
            </Field>
          </dl>
        )}

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default DocumentMetadataDialog;
