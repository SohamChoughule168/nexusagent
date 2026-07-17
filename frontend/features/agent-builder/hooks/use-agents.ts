"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentService } from "../services/agent.service";
import type { Agent, AgentCreatePayload, AgentUpdatePayload, Tool, KnowledgeBase, AgentDetail } from "../types";

/** Query keys for React Query */
export const agentKeys = {
  all: ["agents"] as const,
  lists: () => [...agentKeys.all, "list"] as const,
  list: (filters?: Record<string, unknown>) => [...agentKeys.lists(), { filters }] as const,
  details: () => [...agentKeys.all, "detail"] as const,
  detail: (id: string) => [...agentKeys.details(), id] as const,
  tools: () => [...agentKeys.all, "tools"] as const,
  knowledgeBases: () => [...agentKeys.all, "knowledgeBases"] as const,
  search: (query: string) => [...agentKeys.all, "search", query] as const,
};

/** List all agents */
export function useAgents() {
  return useQuery({
    queryKey: agentKeys.lists(),
    queryFn: () => agentService.listAgents(),
    staleTime: 5 * 60_000, // 5 minutes
  });
}

/** Get a single agent by ID */
export function useAgent(id: string | null) {
  return useQuery({
    queryKey: id ? agentKeys.detail(id) : ["agents", "detail", "null"],
    queryFn: () => agentService.getAgent(id!),
    enabled: !!id,
    staleTime: 5 * 60_000,
  });
}

/** Create agent mutation */
export function useCreateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AgentCreatePayload) => agentService.createAgent(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.lists() });
    },
  });
}

/** Update agent mutation */
export function useUpdateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AgentUpdatePayload }) =>
      agentService.updateAgent(id, payload),
    onSuccess: (updatedAgent, { id }) => {
      // Update the detail cache
      queryClient.setQueryData(agentKeys.detail(id), (old: AgentDetail | undefined) =>
        old ? { ...old, ...updatedAgent, has_changes: false } : old,
      );
      // Invalidate list
      queryClient.invalidateQueries({ queryKey: agentKeys.lists() });
    },
  });
}

/** Delete agent mutation */
export function useDeleteAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => agentService.deleteAgent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.lists() });
    },
  });
}

/** Duplicate agent mutation */
export function useDuplicateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, name }: { id: string; name?: string }) =>
      agentService.duplicateAgent(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.lists() });
    },
  });
}

/** Search agents */
export function useSearchAgents(query: string) {
  return useQuery({
    queryKey: agentKeys.search(query),
    queryFn: () => agentService.searchAgents(query),
    enabled: query.length > 0,
    staleTime: 5 * 60_000,
  });
}

/** List tools */
export function useTools() {
  return useQuery({
    queryKey: agentKeys.tools(),
    queryFn: () => agentService.listTools(),
    staleTime: 10 * 60_000, // 10 minutes
  });
}

/** List knowledge bases */
export function useKnowledgeBases() {
  return useQuery({
    queryKey: agentKeys.knowledgeBases(),
    queryFn: () => agentService.listKnowledgeBases(),
    staleTime: 10 * 60_000, // 10 minutes
  });
}

/** Prefetch agents */
export function usePrefetchAgents() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.prefetchQuery({
      queryKey: agentKeys.lists(),
      queryFn: () => agentService.listAgents(),
      staleTime: 5 * 60_000,
    });
  };
}

/** Transform AgentResponse to AgentDetail */
export function transformAgent(agent: Agent): AgentDetail {
  return {
    ...agent,
    has_changes: false,
  };
}