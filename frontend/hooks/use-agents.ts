"use client";

import { useQuery } from "@tanstack/react-query";
import { conversationService } from "@/services/conversation.service";

/**
 * Agents for the tenant (server state via React Query). Used to let the user
 * pick which agent to chat with when starting a new conversation. Cached for 5
 * minutes since the agent roster changes rarely.
 */
export function useAgents() {
  const query = useQuery({
    queryKey: ["agents"],
    queryFn: () => conversationService.listAgents(),
    staleTime: 5 * 60_000,
  });

  return {
    agents: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export default useAgents;
