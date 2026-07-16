"use client";

import * as React from "react";
import { CheckCircle2, FileUp, Loader2, TriangleAlert, UploadCloud, X } from "lucide-react";
import { useDocuments } from "@/hooks/use-documents";
import { useNotificationStore } from "@/store/notification.store";
import { getErrorMessage } from "@/lib/api-error";
import { formatFileSize } from "@/types/knowledge-base";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/** Backend limits (see app/core/config.py). */
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ACCEPTED_EXT = ["pdf"];
const ACCEPTED_MIME = "application/pdf";

interface UploadTask {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

export interface DocumentUploadProps {
  knowledgeBaseId: string;
}

/**
 * Drag & drop (and click-to-browse) uploader for a knowledge base. Tracks each
 * file's upload progress and surfaces success/error via toasts. New documents
 * appear in the cached document list automatically on success.
 */
export function DocumentUpload({ knowledgeBaseId }: DocumentUploadProps) {
  const { uploadDocumentAsync } = useDocuments(knowledgeBaseId);
  const notify = useNotificationStore();

  const inputRef = React.useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const [tasks, setTasks] = React.useState<UploadTask[]>([]);
  const taskSeq = React.useRef(0);

  const patchTask = React.useCallback(
    (id: string, patch: Partial<UploadTask>) => {
      setTasks((prev) =>
        prev.map((t) => (t.id === id ? { ...t, ...patch } : t)),
      );
    },
    [],
  );

  const validate = (file: File): string | null => {
    const ext = file.name.toLowerCase().split(".").pop() ?? "";
    if (!ACCEPTED_EXT.includes(ext) || file.type !== ACCEPTED_MIME) {
      return "Only PDF files are supported.";
    }
    if (file.size > MAX_FILE_BYTES) {
      return `File exceeds the 50 MB limit (${formatFileSize(file.size)}).`;
    }
    return null;
  };

  const startUpload = React.useCallback(
    async (file: File) => {
      const validationError = validate(file);
      taskSeq.current += 1;
      const id = `upload-${taskSeq.current}`;
      setTasks((prev) => [
        { id, name: file.name, size: file.size, progress: 0, status: "uploading" },
        ...prev,
      ]);

      if (validationError) {
        patchTask(id, { status: "error", error: validationError });
        notify.error("Upload rejected", validationError);
        return;
      }

      try {
        await uploadDocumentAsync({
          file,
          onProgress: (percent) => patchTask(id, { progress: percent }),
        });
        patchTask(id, { status: "done", progress: 100 });
        notify.success("Document uploaded", file.name);
      } catch (err) {
        patchTask(id, { status: "error", error: getErrorMessage(err) });
        notify.error("Upload failed", getErrorMessage(err));
      }
    },
    [uploadDocumentAsync, patchTask, notify],
  );

  const handleFiles = React.useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      Array.from(files).forEach((f) => void startUpload(f));
    },
    [startUpload],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const openPicker = () => inputRef.current?.click();

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload documents. Drag and drop or activate to browse."
        onClick={openPicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openPicker();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-input hover:border-primary/50 hover:bg-accent/30",
        )}
      >
        <UploadCloud className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium">
          Drag &amp; drop PDFs here, or{" "}
          <span className="text-primary underline">browse</span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF only · up to 50 MB each
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {tasks.length > 0 && (
        <ul className="space-y-2">
          {tasks.map((task) => (
            <li
              key={task.id}
              className="rounded-md border bg-card p-3"
              aria-live="polite"
            >
              <div className="flex items-center gap-3">
                <div className="shrink-0">
                  {task.status === "uploading" && (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                  {task.status === "done" && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  )}
                  {task.status === "error" && (
                    <TriangleAlert className="h-4 w-4 text-destructive" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium">{task.name}</p>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatFileSize(task.size)}
                    </span>
                  </div>
                  {task.status === "uploading" ? (
                    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${task.progress}%` }}
                        role="progressbar"
                        aria-valuenow={task.progress}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      />
                    </div>
                  ) : task.error ? (
                    <p className="mt-1 truncate text-xs text-destructive" title={task.error}>
                      {task.error}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">
                      Uploaded
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setTasks((prev) => prev.filter((t) => t.id !== task.id))}
                  aria-label={`Dismiss ${task.name}`}
                  className="shrink-0 rounded-sm text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Button variant="outline" size="sm" onClick={openPicker} className="w-full sm:w-auto">
        <FileUp className="h-4 w-4" />
        Add files
      </Button>
    </div>
  );
}

export default DocumentUpload;
