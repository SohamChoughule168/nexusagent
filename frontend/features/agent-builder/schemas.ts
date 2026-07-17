import { z } from "zod";
import { PARAM_BOUNDS } from "./constants";

/**
 * Zod schema for the Agent Builder form. Mirrors the backend
 * `AgentCreate` / `AgentUpdate` payloads; validation messages are shown inline
 * via React Hook Form. Numeric bounds come from PARAM_BOUNDS so the schema and
 * the slider/input UI never drift.
 */

const numberField = (min: number, max: number, label: string) =>
  z
    .number({ invalid_type_error: `${label} is required` })
    .min(min, `${label} must be ≥ ${min}`)
    .max(max, `${label} must be ≤ ${max}`)
    .refine((v) => !Number.isNaN(v), `${label} is required`);

export const agentFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Name is required")
    .max(100, "Name must be 100 characters or fewer"),
  description: z
    .string()
    .max(500, "Description must be 500 characters or fewer"),
  system_prompt: z
    .string()
    .min(1, "System prompt is required")
    .max(8000, "System prompt must be 8000 characters or fewer"),
  welcome_message: z
    .string()
    .max(500, "Welcome message must be 500 characters or fewer"),
  model_provider: z.string().min(1, "Model provider is required"),
  model_name: z.string().min(1, "Model name is required"),
  temperature: numberField(
    PARAM_BOUNDS.temperature.min,
    PARAM_BOUNDS.temperature.max,
    "Temperature",
  ),
  max_tokens: z
    .number({ invalid_type_error: "Max tokens is required" })
    .int("Max tokens must be a whole number")
    .min(PARAM_BOUNDS.maxTokens.min, "Max tokens must be ≥ 1")
    .max(PARAM_BOUNDS.maxTokens.max, "Max tokens must be ≤ 32768")
    .refine((v) => !Number.isNaN(v), "Max tokens is required"),
  top_p: numberField(PARAM_BOUNDS.topP.min, PARAM_BOUNDS.topP.max, "Top-P"),
  function_calling: z.boolean(),
  multi_agent_routing: z.boolean(),
  streaming: z.boolean(),
  memory_enabled: z.boolean(),
  knowledge_base_ids: z.array(z.string()),
  enabled_tool_ids: z.array(z.string()),
  status: z.enum(["active", "inactive"]),
});

export type AgentFormValues = z.infer<typeof agentFormSchema>;

/** Values used when opening the form to create a brand-new agent. */
export const DEFAULT_AGENT_FORM_VALUES: AgentFormValues = {
  name: "",
  description: "",
  system_prompt: "",
  welcome_message: "",
  model_provider: "openai",
  model_name: "gpt-4o",
  temperature: PARAM_BOUNDS.temperature.default,
  max_tokens: PARAM_BOUNDS.maxTokens.default,
  top_p: PARAM_BOUNDS.topP.default,
  function_calling: false,
  multi_agent_routing: false,
  streaming: true,
  memory_enabled: true,
  knowledge_base_ids: [],
  enabled_tool_ids: [],
  status: "active",
};
