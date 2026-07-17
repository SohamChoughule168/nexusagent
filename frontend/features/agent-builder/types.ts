/** Types for Agent Builder feature */

import type { Agent } from "@/types/conversation";

/** Re-export the domain Agent so feature modules can import it from here. */
export type { Agent } from "@/types/conversation";

/** Agent creation payload */
export interface AgentCreatePayload {
  name: string;
  description?: string | null;
  system_prompt: string;
  welcome_message?: string | null;
  model_provider: string;
  model_name: string;
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  function_calling?: boolean | null;
  multi_agent_routing?: boolean | null;
  streaming?: boolean | null;
  memory_enabled?: boolean | null;
  knowledge_base_ids?: string[] | null;
  enabled_tool_ids?: string[] | null;
}

/** Agent update payload */
export interface AgentUpdatePayload {
  name?: string;
  description?: string | null;
  system_prompt?: string;
  welcome_message?: string | null;
  model_provider?: string;
  model_name?: string;
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  function_calling?: boolean | null;
  multi_agent_routing?: boolean | null;
  streaming?: boolean | null;
  memory_enabled?: boolean | null;
  knowledge_base_ids?: string[] | null;
  enabled_tool_ids?: string[] | null;
  status?: string;
}

/** Agent form state */
export interface AgentFormState {
  id?: string;
  name: string;
  description: string;
  system_prompt: string;
  welcome_message: string;
  model_provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  top_p: number;
  function_calling: boolean;
  multi_agent_routing: boolean;
  streaming: boolean;
  memory_enabled: boolean;
  knowledge_base_ids: string[];
  enabled_tool_ids: string[];
  status: "active" | "inactive";
}

/** Extended Agent with UI state */
export interface AgentDetail extends Agent {
  has_changes: boolean;
}

/** Agent API response */
export interface AgentResponse {
  id: string;
  public_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  model_provider: string | null;
  model_name: string | null;
  temperature: number | null;
  max_tokens: number | null;
  top_p: number | null;
  function_calling: boolean | null;
  multi_agent_routing: boolean | null;
  streaming: boolean | null;
  memory_enabled: boolean | null;
  status: string;
  config: Record<string, unknown> | null;
  knowledge_base_ids: string[] | null;
  enabled_tool_ids: string[] | null;
  created_at: string;
  updated_at: string | null;
}

/** Tool type for assignment */
export interface Tool {
  id: string;
  name: string;
  description: string;
  type: "function" | "tool";
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
}

/** Knowledge Base type for assignment */
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  embedding_model: string | null;
  status: string;
  document_count: number;
  created_at: string;
  updated_at: string | null;
}

/** Model option for dropdown */
export interface ModelOption {
  value: string;
  label: string;
  provider: string;
}