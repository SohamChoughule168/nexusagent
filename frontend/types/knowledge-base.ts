/**
 * Domain types for the Knowledge Base module, mirroring the backend
 * `/knowledge-bases/*` and `/documents/*` schemas so the frontend never
 * re-implements backend validation.
 *
 * Backend sources:
 *   - app/schemas/knowledge_base.py  (KnowledgeBaseCreate/Update/Response)
 *   - app/schemas/document.py        (DocumentResponse)
 *
 * IDs are UUIDs serialized as strings by the backend.
 */

/** A knowledge base, as returned by GET /knowledge-bases and POST/PUT. */
export interface KnowledgeBase {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  chunk_strategy: string;
  retrieval_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string | null;
}

/** Body for POST /knowledge-bases/ (name required; rest use backend defaults). */
export interface KnowledgeBaseCreatePayload {
  name: string;
  description?: string | null;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  chunk_strategy?: string;
  retrieval_config?: Record<string, unknown> | null;
}

/** Body for PUT /knowledge-bases/{id} (all fields optional). */
export interface KnowledgeBaseUpdatePayload {
  name?: string;
  description?: string | null;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  chunk_strategy?: string;
  retrieval_config?: Record<string, unknown> | null;
}

/**
 * Document lifecycle states. The backend drives these:
 *   - `uploaded`  : raw bytes stored, not yet processed
 *   - `processed` : text extracted + chunked (ingested), not embedded
 *   - `indexed`   : chunks embedded + indexed for retrieval
 *   - `failed`    : processing errored (see `error_message`)
 */
export type DocumentStatus = "uploaded" | "processed" | "indexed" | "failed";

/** A stored document + its processing metadata. */
export interface Document {
  id: string;
  knowledge_base_id: string;
  organization_id: string;
  filename: string;
  original_filename: string;
  title: string | null;
  mime_type: string;
  file_size: number;
  storage_path: string;
  status: DocumentStatus | string;
  page_count: number | null;
  chunk_count: number | null;
  error_message: string | null;
  upload_member_id: string;
  embedding_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

/** Options for an upload, including a progress callback. */
export interface UploadDocumentOptions {
  title?: string | null;
  /** Invoked with 0-100 as bytes are sent. */
  onProgress?: (percent: number) => void;
  /** Aborts the in-flight upload when set. */
  signal?: AbortSignal;
}

/** Human label for a document status. */
export function documentStatusLabel(status: Document["status"]): string {
  switch (status) {
    case "uploaded":
      return "Uploaded";
    case "processed":
      return "Processed";
    case "indexed":
      return "Indexed";
    case "failed":
      return "Failed";
    default:
      return String(status).charAt(0).toUpperCase() + String(status).slice(1);
  }
}

/** Tailwind badge variant for a document status. */
export function documentStatusVariant(
  status: Document["status"],
): "secondary" | "default" | "success" | "destructive" | "outline" {
  switch (status) {
    case "uploaded":
      return "secondary";
    case "processed":
      return "default";
    case "indexed":
      return "success";
    case "failed":
      return "destructive";
    default:
      return "outline";
  }
}

/** Format a byte count into a human-readable size (B/KB/MB). */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

/** Embedding models offered in the create/edit form. */
export const EMBEDDING_MODELS = [
  "text-embedding-3-small",
  "text-embedding-3-large",
  "text-embedding-ada-002",
] as const;

/** Chunking strategies offered in the create/edit form. */
export const CHUNK_STRATEGIES = ["recursive", "fixed", "character"] as const;
