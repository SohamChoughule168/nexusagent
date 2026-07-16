"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { knowledgeBaseService } from "@/services/knowledge-base.service";
import type {
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseUpdatePayload,
} from "@/types/knowledge-base";

/** Stable React Query keys for knowledge bases. */
export const knowledgeBaseKeys = {
  all: ["knowledge-bases"] as const,
  detail: (id: string) => ["knowledge-bases", id] as const,
};

/** Read/update the cached KB list with optimistic updates. */
function patchList(
  qc: QueryClient,
  id: string,
  patch: Partial<KnowledgeBase>,
) {
  qc.setQueryData<KnowledgeBase[]>(knowledgeBaseKeys.all, (old) =>
    (old ?? []).map((kb) => (kb.id === id ? { ...kb, ...patch } : kb)),
  );
}

/**
 * Knowledge bases: list (server state via React Query) plus create / update /
 * delete mutations with optimistic cache updates so the list feels instant.
 */
export function useKnowledgeBases() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: knowledgeBaseKeys.all,
    queryFn: () => knowledgeBaseService.listKnowledgeBases(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: KnowledgeBaseCreatePayload) =>
      knowledgeBaseService.createKnowledgeBase(payload),
    onSuccess: (created) => {
      qc.setQueryData<KnowledgeBase[]>(knowledgeBaseKeys.all, (old) => [
        created,
        ...(old ?? []),
      ]);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: KnowledgeBaseUpdatePayload;
    }) => knowledgeBaseService.updateKnowledgeBase(id, payload),
    onMutate: async ({ id, payload }) => {
      await qc.cancelQueries({ queryKey: knowledgeBaseKeys.all });
      const prev = qc.getQueryData<KnowledgeBase[]>(knowledgeBaseKeys.all);
      patchList(qc, id, payload as Partial<KnowledgeBase>);
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(knowledgeBaseKeys.all, ctx.prev);
    },
    onSuccess: (updated) => {
      patchList(qc, updated.id, updated);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => knowledgeBaseService.deleteKnowledgeBase(id),
    onSuccess: (_res, id) => {
      qc.setQueryData<KnowledgeBase[]>(knowledgeBaseKeys.all, (old) =>
        (old ?? []).filter((kb) => kb.id !== id),
      );
    },
  });

  return {
    knowledgeBases: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,

    createKnowledgeBase: createMutation.mutate,
    createKnowledgeBaseAsync: createMutation.mutateAsync,
    isCreating: createMutation.isPending,

    updateKnowledgeBase: updateMutation.mutate,
    updateKnowledgeBaseAsync: updateMutation.mutateAsync,
    isUpdating: updateMutation.isPending,

    deleteKnowledgeBase: deleteMutation.mutate,
    deleteKnowledgeBaseAsync: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
  };
}

export default useKnowledgeBases;
