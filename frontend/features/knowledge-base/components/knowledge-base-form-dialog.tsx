"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  CHUNK_STRATEGIES,
  EMBEDDING_MODELS,
  type KnowledgeBase,
  type KnowledgeBaseCreatePayload,
} from "@/types/knowledge-base";
import { cn } from "@/lib/utils";

export interface KnowledgeBaseFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, the dialog edits this KB; otherwise it creates a new one. */
  initial?: KnowledgeBase | null;
  onSubmit: (payload: KnowledgeBaseCreatePayload) => void | Promise<void>;
  isSubmitting?: boolean;
}

const SELECT_CLASS =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Create / edit dialog for a knowledge base. Controlled local state mirrors
 * the backend `KnowledgeBaseCreate`/`KnowledgeBaseUpdate` fields; `name` is
 * required. On submit it emits the full payload (including defaults) so the
 * service layer sends exactly what the API expects.
 */
export function KnowledgeBaseFormDialog({
  open,
  onOpenChange,
  initial,
  onSubmit,
  isSubmitting = false,
}: KnowledgeBaseFormDialogProps) {
  const isEdit = Boolean(initial);

  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [embeddingModel, setEmbeddingModel] = React.useState<string>(
    EMBEDDING_MODELS[0],
  );
  const [chunkStrategy, setChunkStrategy] = React.useState<string>(
    CHUNK_STRATEGIES[0],
  );
  const [chunkSize, setChunkSize] = React.useState("1000");
  const [chunkOverlap, setChunkOverlap] = React.useState("200");
  const [nameError, setNameError] = React.useState<string | null>(null);

  // Re-seed the form whenever the dialog opens (create or edit).
  React.useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setDescription(initial?.description ?? "");
    setEmbeddingModel(initial?.embedding_model ?? EMBEDDING_MODELS[0]);
    setChunkStrategy(initial?.chunk_strategy ?? CHUNK_STRATEGIES[0]);
    setChunkSize(String(initial?.chunk_size ?? 1000));
    setChunkOverlap(String(initial?.chunk_overlap ?? 200));
    setNameError(null);
  }, [open, initial]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError("Name is required");
      return;
    }
    const size = Number.parseInt(chunkSize, 10);
    const overlap = Number.parseInt(chunkOverlap, 10);
    const payload: KnowledgeBaseCreatePayload = {
      name: name.trim(),
      description: description.trim() ? description.trim() : null,
      embedding_model: embeddingModel,
      chunk_strategy: chunkStrategy,
      chunk_size: Number.isFinite(size) ? size : 1000,
      chunk_overlap: Number.isFinite(overlap) ? overlap : 200,
    };
    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit knowledge base" : "New knowledge base"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update how documents are chunked and embedded."
              : "Configure how documents are chunked and embedded."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="kb-name">Name</Label>
            <Input
              id="kb-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (nameError) setNameError(null);
              }}
              placeholder="Product manuals"
              aria-invalid={Boolean(nameError)}
              disabled={isSubmitting}
              autoFocus
            />
            {nameError && (
              <p className="text-sm text-destructive">{nameError}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-description">Description</Label>
            <Textarea
              id="kb-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this knowledge base used for?"
              disabled={isSubmitting}
              rows={3}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="kb-embedding">Embedding model</Label>
              <select
                id="kb-embedding"
                className={cn(SELECT_CLASS, "capitalize")}
                value={embeddingModel}
                onChange={(e) => setEmbeddingModel(e.target.value)}
                disabled={isSubmitting}
              >
                {EMBEDDING_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kb-strategy">Chunk strategy</Label>
              <select
                id="kb-strategy"
                className={cn(SELECT_CLASS, "capitalize")}
                value={chunkStrategy}
                onChange={(e) => setChunkStrategy(e.target.value)}
                disabled={isSubmitting}
              >
                {CHUNK_STRATEGIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kb-chunk-size">Chunk size (tokens)</Label>
              <Input
                id="kb-chunk-size"
                type="number"
                min={1}
                value={chunkSize}
                onChange={(e) => setChunkSize(e.target.value)}
                disabled={isSubmitting}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kb-chunk-overlap">Chunk overlap (tokens)</Label>
              <Input
                id="kb-chunk-overlap"
                type="number"
                min={0}
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isEdit ? "Save changes" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default KnowledgeBaseFormDialog;
