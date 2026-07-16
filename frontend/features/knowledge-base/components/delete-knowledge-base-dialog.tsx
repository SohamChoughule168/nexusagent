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
import type { KnowledgeBase } from "@/types/knowledge-base";

export interface DeleteKnowledgeBaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeBase: KnowledgeBase | null;
  onConfirm: (id: string) => void | Promise<void>;
  isDeleting?: boolean;
}

/**
 * Confirmation dialog for deleting a knowledge base. Destructive action, so it
 * uses the destructive button variant and names the target explicitly.
 */
export function DeleteKnowledgeBaseDialog({
  open,
  onOpenChange,
  knowledgeBase,
  onConfirm,
  isDeleting = false,
}: DeleteKnowledgeBaseDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete knowledge base?</DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span className="font-medium text-foreground">
              {knowledgeBase?.name}
            </span>{" "}
            and all of its documents and indexed chunks. This cannot be undone.
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
            onClick={() => knowledgeBase && onConfirm(knowledgeBase.id)}
            disabled={isDeleting || !knowledgeBase}
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

export default DeleteKnowledgeBaseDialog;
