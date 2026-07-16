import apiClient from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import type {
  Document,
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseUpdatePayload,
  UploadDocumentOptions,
} from "@/types/knowledge-base";

/**
 * Knowledge Base service — the single place that talks to the backend
 * `/knowledge-bases/*` and `/documents/*` endpoints. Reuses the shared Axios
 * `apiClient` so the auth + refresh interceptors still apply.
 *
 * Upload uses a `multipart/form-data` body (with an `onUploadProgress`
 * callback for the progress bar) and therefore must not send the JSON
 * `Content-Type` default — the header is overridden to `multipart/form-data`.
 */
export const knowledgeBaseService = {
  /** List knowledge bases for the authenticated tenant. */
  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    const { data } = await apiClient.get<KnowledgeBase[]>("/knowledge-bases/");
    return data;
  },

  /** Create a knowledge base. */
  async createKnowledgeBase(
    payload: KnowledgeBaseCreatePayload,
  ): Promise<KnowledgeBase> {
    const { data } = await apiClient.post<KnowledgeBase>(
      "/knowledge-bases/",
      payload,
    );
    return data;
  },

  /** Fetch a single knowledge base by id. */
  async getKnowledgeBase(id: string): Promise<KnowledgeBase> {
    const { data } = await apiClient.get<KnowledgeBase>(
      `/knowledge-bases/${id}`,
    );
    return data;
  },

  /** Update a knowledge base (partial payload). */
  async updateKnowledgeBase(
    id: string,
    payload: KnowledgeBaseUpdatePayload,
  ): Promise<KnowledgeBase> {
    const { data } = await apiClient.put<KnowledgeBase>(
      `/knowledge-bases/${id}`,
      payload,
    );
    return data;
  },

  /** Delete a knowledge base (204 No Content). */
  async deleteKnowledgeBase(id: string): Promise<void> {
    await apiClient.delete(`/knowledge-bases/${id}`);
  },

  /** List documents for a knowledge base. */
  async listDocuments(knowledgeBaseId: string): Promise<Document[]> {
    const { data } = await apiClient.get<Document[]>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
    );
    return data;
  },

  /**
   * Upload a document (PDF) into a knowledge base. Tracks upload progress via
   * `onProgress` and supports aborting via `signal`.
   */
  async uploadDocument(
    knowledgeBaseId: string,
    file: File,
    options: UploadDocumentOptions = {},
  ): Promise<Document> {
    const form = new FormData();
    form.append("file", file, file.name);
    if (options.title) form.append("title", options.title);

    const { data } = await apiClient.post<Document>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (!options.onProgress || !e.total) return;
          const percent = Math.min(
            100,
            Math.round((e.loaded / e.total) * 100),
          );
          options.onProgress(percent);
        },
        signal: options.signal,
      },
    );
    return data;
  },

  /** Fetch a single document's metadata. */
  async getDocument(id: string): Promise<Document> {
    const { data } = await apiClient.get<Document>(`/documents/${id}`);
    return data;
  },

  /** Delete a document (204 No Content). */
  async deleteDocument(id: string): Promise<void> {
    await apiClient.delete(`/documents/${id}`);
  },

  /** Extract text + chunk a document (sets status `processed`). */
  async ingestDocument(id: string): Promise<Document> {
    const { data } = await apiClient.post<Document>(
      `/documents/${id}/ingest`,
    );
    return data;
  },

  /** Embed a document's chunks + index it (sets status `indexed`). */
  async embedDocument(id: string): Promise<Document> {
    const { data } = await apiClient.post<Document>(
      `/documents/${id}/embed`,
    );
    return data;
  },
};

export default knowledgeBaseService;

/** Re-export the typed error so consumers can branch on `code`/`status`. */
export { ApiError };
