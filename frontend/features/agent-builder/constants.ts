/**
 * Static option sets for the Agent Builder form. These mirror the model
 * providers/models offered by the backend without re-implementing server-side
 * configuration. Keep in sync with backend/app/schemas/agent.py if it changes.
 */

export interface ModelOptionGroup {
  value: string;
  label: string;
}

/** Model providers selectable in the agent form. */
export const MODEL_PROVIDERS: ModelOptionGroup[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "google", label: "Google" },
];

/** Models grouped by provider. Used to populate the dependent model dropdown. */
export const MODELS_BY_PROVIDER: Record<string, ModelOptionGroup[]> = {
  openai: [
    { value: "gpt-4o", label: "GPT-4o" },
    { value: "gpt-4o-mini", label: "GPT-4o mini" },
    { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
  ],
  anthropic: [
    { value: "claude-opus-4", label: "Claude Opus 4" },
    { value: "claude-sonnet-4", label: "Claude Sonnet 4" },
    { value: "claude-haiku-4", label: "Claude Haiku 4" },
  ],
  openrouter: [
    { value: "anthropic/claude-3.5-sonnet", label: "Claude 3.5 Sonnet" },
    { value: "openai/gpt-4o", label: "GPT-4o" },
  ],
  google: [
    { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
  ],
};

/** Default generation-parameter bounds, surfaced in the form help text. */
export const PARAM_BOUNDS = {
  temperature: { min: 0, max: 2, step: 0.1, default: 0.7 },
  maxTokens: { min: 1, max: 32768, step: 1, default: 1024 },
  topP: { min: 0, max: 1, step: 0.05, default: 1 },
} as const;

/** Human labels for the capability toggles. */
export const CAPABILITY_LABELS = {
  function_calling: {
    title: "Function Calling",
    description: "Let the agent invoke tools/functions to answer requests.",
  },
  multi_agent_routing: {
    title: "Multi-Agent Routing",
    description: "Route complex tasks to specialized sub-agents.",
  },
  streaming: {
    title: "Streaming",
    description: "Stream token-by-token responses in chat.",
  },
  memory_enabled: {
    title: "Conversation Memory",
    description:
      "Persist conversation history so the agent remembers prior turns.",
  },
} as const;
