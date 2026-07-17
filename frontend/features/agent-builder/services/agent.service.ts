import apiClient from "@/lib/api-client";
import type {
  Agent,
  AgentCreatePayload,
  AgentUpdatePayload,
  AgentResponse,
  Tool,
  KnowledgeBase,
  AgentDetail,
} from "../types";

/**
 * Agent service — handles agent CRUD operations and related resources.
 * Reuses the shared apiClient for request/response handling.
 */

export const agentService = {
  /** List all agents for the tenant */
  async listAgents(): Promise<AgentDetail[]> {
    const { data } = await apiClient.get<AgentResponse[]>("/agents/");
    return data.map((agent) => ({
      ...agent,
      has_changes: false,
    }));
  },

  /** Get a single agent by ID */
  async getAgent(id: string): Promise<AgentDetail> {
    const { data } = await apiClient.get<AgentResponse>(`/agents/${id}`);
    return {
      ...data,
      has_changes: false,
    };
  },

  /** Create a new agent */
  async createAgent(payload: AgentCreatePayload): Promise<Agent> {
    const { data } = await apiClient.post<Agent>("/agents/", payload);
    return data;
  },

  /** Update an existing agent */
  async updateAgent(id: string, payload: AgentUpdatePayload): Promise<Agent> {
    const { data } = await apiClient.patch<Agent>(`/agents/${id}`, payload);
    return data;
  },

  /** Delete an agent */
  async deleteAgent(id: string): Promise<void> {
    await apiClient.delete(`/agents/${id}`);
  },

  /** Duplicate an agent */
  async duplicateAgent(id: string, name?: string): Promise<Agent> {
    const { data } = await apiClient.post<Agent>(`/agents/${id}/duplicate`, {
      name,
    });
    return data;
  },

  /** Search agents by name */
  async searchAgents(query: string): Promise<AgentDetail[]> {
    const { data } = await apiClient.get<AgentResponse[]>(
      `/agents/search?q=${encodeURIComponent(query)}`,
    );
    return data.map((agent) => ({
      ...agent,
      has_changes: false,
    }));
  },

  /** List available tools */
  async listTools(): Promise<Tool[]> {
    const { data } = await apiClient.get<Tool[]>("/tools/");
    return data;
  },

  /** List knowledge bases */
  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    const { data } = await apiClient.get<KnowledgeBase[]>("/knowledge-bases/");
    return data;
  },
};

export default agentService;