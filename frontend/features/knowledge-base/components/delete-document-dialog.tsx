"use client";

import * as React from "react";
import { Loader2, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { Document } from "@/types/knowledge-base";

export interface DeleteDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  document: Document | null;
  onConfirm: (id: string) => void | Promise<void>;
  isDeleting?: boolean;
}

/**
 * Confirmation dialog for deleting a document. Names the target file and notes
 * that indexed chunks are removed with it.
 */
export function DeleteDocumentDialog({
  open,
  onOpenChange,
  document,
  onConfirm,
  isDeleting = false,
}: DeleteDocumentDialogProps) {
  const label = document?.title || document?.filename || "this document";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete document?</DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span className="font-medium text-foreground">{label}</span> and its
            indexed chunks. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => document && onConfirm(document.id)}
            disabled={isDeleting || !document}
          >
            {isDeleting && <Loader2 className="h-4 w-4 animate-spin" />}
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default DeleteDocumentDialog;
