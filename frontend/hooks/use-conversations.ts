"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { conversationService } from "@/services/conversation.service";
import type {
  Conversation,
  ConversationCreatePayload,
  ConversationUpdatePayload,
} from "@/types/conversation";

/** Stable React Query keys for conversations. */
export const conversationKeys = {
  all: ["conversations"] as const,
};

/** Read/update the cached conversation list with optimistic updates. */
function patchConversation(
  qc: QueryClient,
  id: string,
  patch: Partial<Conversation>,
) {
  qc.setQueryData<Conversation[]>(conversationKeys.all, (old) =>
    (old ?? []).map((c) => (c.id === id ? { ...c, ...patch } : c)),
  );
}

/**
 * Conversations: list (server state via React Query) plus create / rename /
 * delete mutations with optimistic cache updates so the list feels instant.
 */
export function useConversations() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: conversationKeys.all,
    queryFn: () => conversationService.listConversations(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ConversationCreatePayload) =>
      conversationService.createConversation(payload),
    onSuccess: (created) => {
      qc.setQueryData<Conversation[]>(conversationKeys.all, (old) => [
        created,
        ...(old ?? []),
      ]);
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ConversationUpdatePayload }) =>
      conversationService.updateConversation(id, payload),
    onMutate: async ({ id, payload }) => {
      await qc.cancelQueries({ queryKey: conversationKeys.all });
      const prev = qc.getQueryData<Conversation[]>(conversationKeys.all);
      patchConversation(qc, id, payload);
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(conversationKeys.all, ctx.prev);
    },
    onSuccess: (updated) => {
      patchConversation(qc, updated.id, updated);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => conversationService.deleteConversation(id),
    onSuccess: (_res, id) => {
      qc.setQueryData<Conversation[]>(conversationKeys.all, (old) =>
        (old ?? []).filter((c) => c.id !== id),
      );
    },
  });

  return {
    conversations: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,

    createConversation: createMutation.mutate,
    createConversationAsync: createMutation.mutateAsync,
    isCreating: createMutation.isPending,

    renameConversation: renameMutation.mutate,
    renameConversationAsync: renameMutation.mutateAsync,
    isRenaming: renameMutation.isPending,

    deleteConversation: deleteMutation.mutate,
    deleteConversationAsync: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
  };
}

export default useConversations;
