import type {
  AgentCreatePayload,
  AgentUpdatePayload,
  AgentDetail,
} from "./types";
import {
  DEFAULT_AGENT_FORM_VALUES,
  type AgentFormValues,
} from "./schemas";
import { PARAM_BOUNDS } from "./constants";

/** Map a stored Agent (or its detail) onto the form's flat value shape. */
export function agentToFormValues(agent: AgentDetail): AgentFormValues {
  return {
    name: agent.name,
    description: agent.description ?? "",
    system_prompt: agent.system_prompt,
    welcome_message: agent.welcome_message ?? "",
    model_provider: agent.model_provider ?? DEFAULT_AGENT_FORM_VALUES.model_provider,
    model_name: agent.model_name ?? DEFAULT_AGENT_FORM_VALUES.model_name,
    temperature: agent.temperature ?? PARAM_BOUNDS.temperature.default,
    max_tokens: agent.max_tokens ?? PARAM_BOUNDS.maxTokens.default,
    top_p: agent.top_p ?? PARAM_BOUNDS.topP.default,
    function_calling: Boolean(agent.function_calling),
    multi_agent_routing: Boolean(agent.multi_agent_routing),
    streaming: agent.streaming ?? true,
    memory_enabled: agent.memory_enabled ?? true,
    knowledge_base_ids: agent.knowledge_base_ids ?? [],
    enabled_tool_ids: agent.enabled_tool_ids ?? [],
    status: agent.status === "inactive" ? "inactive" : "active",
  };
}

const toPayloadBase = (v: AgentFormValues) => ({
  name: v.name.trim(),
  description: v.description.trim() ? v.description.trim() : null,
  system_prompt: v.system_prompt,
  welcome_message: v.welcome_message.trim() ? v.welcome_message.trim() : null,
  model_provider: v.model_provider,
  model_name: v.model_name,
  temperature: v.temperature,
  max_tokens: v.max_tokens,
  top_p: v.top_p,
  function_calling: v.function_calling,
  multi_agent_routing: v.multi_agent_routing,
  streaming: v.streaming,
  memory_enabled: v.memory_enabled,
  knowledge_base_ids: v.knowledge_base_ids,
  enabled_tool_ids: v.enabled_tool_ids,
});

/** Build the create payload (no `status` — backend defaults to active). */
export function buildCreatePayload(v: AgentFormValues): AgentCreatePayload {
  return toPayloadBase(v);
}

/** Build the update payload (includes `status`). */
export function buildUpdatePayload(v: AgentFormValues): AgentUpdatePayload {
  return { ...toPayloadBase(v), status: v.status };
}
