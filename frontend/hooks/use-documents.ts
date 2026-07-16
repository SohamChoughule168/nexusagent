"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { knowledgeBaseService } from "@/services/knowledge-base.service";
import type { Document } from "@/types/knowledge-base";

/** Stable React Query keys for documents within a knowledge base. */
export const documentKeys = {
  list: (knowledgeBaseId: string | null) =>
    ["documents", knowledgeBaseId] as const,
};

/** Read/replace a KB's document list in the cache. */
function setDocs(
  qc: QueryClient,
  knowledgeBaseId: string,
  next: Document[] | ((old: Document[] | undefined) => Document[]),
) {
  qc.setQueryData<Document[]>(documentKeys.list(knowledgeBaseId), (old) =>
    typeof next === "function" ? (next as (o: Document[] | undefined) => Document[])(old) : next,
  );
}

/**
 * Documents for a single knowledge base (server state via React Query).
 * Includes upload (with progress), delete, ingest and embed mutations, plus a
 * `process` helper that runs ingest -> embed sequentially so a freshly
 * uploaded document reaches the `indexed` (retrievable) state.
 *
 * Mutations optimistically reflect status changes in the cached list so the
 * UI does not flicker between steps.
 */
export function useDocuments(knowledgeBaseId: string | null) {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: documentKeys.list(knowledgeBaseId),
    queryFn: () => knowledgeBaseService.listDocuments(knowledgeBaseId as string),
    enabled: Boolean(knowledgeBaseId),
  });

  const uploadMutation = useMutation({
    mutationFn: ({
      file,
      title,
      onProgress,
      signal,
    }: {
      file: File;
      title?: string | null;
      onProgress?: (percent: number) => void;
      signal?: AbortSignal;
    }) =>
      knowledgeBaseService.uploadDocument(knowledgeBaseId as string, file, {
        title,
        onProgress,
        signal,
      }),
    onSuccess: (doc) => {
      setDocs(qc, knowledgeBaseId as string, (old) => [doc, ...(old ?? [])]);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => knowledgeBaseService.deleteDocument(id),
    onSuccess: (_res, id) => {
      setDocs(qc, knowledgeBaseId as string, (old) =>
        (old ?? []).filter((d) => d.id !== id),
      );
    },
  });

  const ingestMutation = useMutation({
    mutationFn: (id: string) => knowledgeBaseService.ingestDocument(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: documentKeys.list(knowledgeBaseId) });
      const prev = qc.getQueryData<Document[]>(documentKeys.list(knowledgeBaseId));
      setDocs(qc, knowledgeBaseId as string, (old) =>
        (old ?? []).map((d) =>
          d.id === id ? { ...d, status: "processed", error_message: null } : d,
        ),
      );
      return { prev };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) setDocs(qc, knowledgeBaseId as string, ctx.prev);
    },
    onSuccess: (updated) => {
      setDocs(qc, knowledgeBaseId as string, (old) =>
        (old ?? []).map((d) => (d.id === updated.id ? updated : d)),
      );
    },
  });

  const embedMutation = useMutation({
    mutationFn: (id: string) => knowledgeBaseService.embedDocument(id),
    onSuccess: (updated) => {
      setDocs(qc, knowledgeBaseId as string, (old) =>
        (old ?? []).map((d) => (d.id === updated.id ? updated : d)),
      );
    },
  });

  /** Ingest then embed a document in one step (used by the "Process" action). */
  const process = async (id: string) => {
    const ingested = await ingestMutation.mutateAsync(id);
    return embedMutation.mutateAsync(ingested.id);
  };

  return {
    documents: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,

    uploadDocument: uploadMutation.mutate,
    uploadDocumentAsync: uploadMutation.mutateAsync,
    isUploading: uploadMutation.isPending,

    deleteDocument: deleteMutation.mutate,
    deleteDocumentAsync: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,

    ingestDocument: ingestMutation.mutate,
    ingestDocumentAsync: ingestMutation.mutateAsync,
    isIngesting: ingestMutation.isPending,

    embedDocument: embedMutation.mutate,
    embedDocumentAsync: embedMutation.mutateAsync,
    isEmbedding: embedMutation.isPending,

    processDocument: process,
  };
}

export default useDocuments;
