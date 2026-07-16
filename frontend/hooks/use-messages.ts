"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationService } from "@/services/conversation.service";
import type { Message } from "@/types/conversation";

/** Stable React Query keys for a conversation's messages. */
export const messageKeys = {
  list: (conversationId: string | null) =>
    ["messages", conversationId] as const,
};

/**
 * Messages for a single conversation (server state via React Query).
 * Disabled until a conversation is selected. `invalidate` refetches after a
 * stream completes so persisted user/assistant messages replace optimistic ones.
 */
export function useMessages(conversationId: string | null) {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: messageKeys.list(conversationId),
    queryFn: () =>
      conversationService.listMessages(conversationId as string),
    enabled: Boolean(conversationId),
  });

  const invalidate = () => {
    if (conversationId) {
      qc.invalidateQueries({ queryKey: messageKeys.list(conversationId) });
    }
  };

  const appendOptimistic = (message: Message) => {
    if (!conversationId) return;
    qc.setQueryData<Message[]>(messageKeys.list(conversationId), (old) => [
      ...(old ?? []),
      message,
    ]);
  };

  return {
    messages: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
    appendOptimistic,
  };
}

export default useMessages;
