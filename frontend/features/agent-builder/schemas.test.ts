import { describe, it, expect } from "vitest";
import { agentFormSchema, DEFAULT_AGENT_FORM_VALUES } from "@/features/agent-builder/schemas";
import {
  agentToFormValues,
  buildCreatePayload,
  buildUpdatePayload,
} from "@/features/agent-builder/transform";
import type { AgentDetail } from "@/features/agent-builder/types";

describe("agentFormSchema", () => {
  it("accepts filled-in values based on the defaults", () => {
    expect(
      agentFormSchema.safeParse({
        ...DEFAULT_AGENT_FORM_VALUES,
        name: "My Agent",
        system_prompt: "Be helpful.",
      }).success,
    ).toBe(true);
  });

  it("rejects the empty defaults (name + system prompt required)", () => {
    expect(agentFormSchema.safeParse(DEFAULT_AGENT_FORM_VALUES).success).toBe(
      false,
    );
  });

  it("rejects empty name and system prompt", () => {
    const result = agentFormSchema.safeParse({
      ...DEFAULT_AGENT_FORM_VALUES,
      name: "",
      system_prompt: "",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const fields = result.error.issues.map((i) => i.path[0]);
      expect(fields).toContain("name");
      expect(fields).toContain("system_prompt");
    }
  });

  it("enforces temperature bounds", () => {
    expect(
      agentFormSchema.safeParse({
        ...DEFAULT_AGENT_FORM_VALUES,
        temperature: 5,
      }).success,
    ).toBe(false);
  });

  it("requires whole-number max tokens", () => {
    expect(
      agentFormSchema.safeParse({
        ...DEFAULT_AGENT_FORM_VALUES,
        max_tokens: 1.5,
      }).success,
    ).toBe(false);
  });
});

describe("transform helpers", () => {
  const agent: AgentDetail = {
    id: "a1",
    public_id: "pub1",
    name: "Support Agent",
    description: null,
    system_prompt: "Be helpful.",
    welcome_message: null,
    model_provider: null,
    model_name: null,
    temperature: null,
    max_tokens: null,
    top_p: null,
    function_calling: null,
    multi_agent_routing: null,
    streaming: null,
    memory_enabled: null,
    status: "inactive",
    config: null,
    knowledge_base_ids: null,
    enabled_tool_ids: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    has_changes: false,
  };

  it("fills defaults from a sparse agent", () => {
    const values = agentToFormValues(agent);
    expect(values.model_provider).toBe("openai");
    expect(values.temperature).toBe(0.7);
    expect(values.knowledge_base_ids).toEqual([]);
    expect(values.status).toBe("inactive");
  });

  it("omits status from the create payload but includes it in update", () => {
    const values = agentToFormValues(agent);
    expect(buildCreatePayload(values)).not.toHaveProperty("status");
    expect(buildUpdatePayload(values).status).toBe("inactive");
  });

  it("nulls empty description / welcome message in the payload", () => {
    const values = agentToFormValues(agent);
    const payload = buildCreatePayload(values);
    expect(payload.description).toBeNull();
    expect(payload.welcome_message).toBeNull();
  });
});
