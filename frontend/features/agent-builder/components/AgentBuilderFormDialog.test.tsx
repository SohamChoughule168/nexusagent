import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AgentBuilderFormDialog } from "@/features/agent-builder/components/AgentBuilderFormDialog";
import type { AgentDetail, Tool, KnowledgeBase } from "@/features/agent-builder/types";

const kbFixture: KnowledgeBase = {
  id: "kb1",
  name: "Docs KB",
  description: "Product docs",
  embedding_model: "text-embedding-3-small",
  status: "indexed",
  document_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

const toolFixture: Tool = {
  id: "t1",
  name: "Web Search",
  description: "Search the web",
  type: "function",
  config: {},
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

vi.mock("@/features/agent-builder/hooks/use-agents", () => ({
  useTools: () => ({ data: [toolFixture], isLoading: false }),
  useKnowledgeBases: () => ({ data: [kbFixture], isLoading: false }),
}));

const detailFixture: AgentDetail = {
  id: "a1",
  public_id: "pub1",
  name: "Support Agent",
  description: "Helps users",
  system_prompt: "You are helpful.",
  welcome_message: "Hi!",
  model_provider: "anthropic",
  model_name: "claude-opus-4",
  temperature: 0.5,
  max_tokens: 2048,
  top_p: 0.9,
  function_calling: true,
  multi_agent_routing: false,
  streaming: true,
  memory_enabled: true,
  status: "active",
  config: null,
  knowledge_base_ids: ["kb1"],
  enabled_tool_ids: ["t1"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  has_changes: false,
};

describe("AgentBuilderFormDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the create form with sensible defaults", () => {
    render(
      <AgentBuilderFormDialog
        open
        onOpenChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("System prompt")).toHaveValue("");
    expect(screen.getByLabelText("Max tokens")).toHaveValue(1024);
    expect(screen.getByLabelText("Top-P")).toHaveValue(1);
    expect(screen.getByText("0.7")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create agent/i }),
    ).toBeInTheDocument();
  });

  it("blocks submit and shows validation errors for required fields", async () => {
    const onSubmit = vi.fn();
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(screen.getByText("System prompt is required")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid create payload with defaults", async () => {
    const onSubmit = vi.fn();
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "My Agent" },
    });
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Be helpful." },
    });
    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.name).toBe("My Agent");
    expect(payload.system_prompt).toBe("Be helpful.");
    expect(payload.model_provider).toBe("openai");
    expect(payload.model_name).toBe("gpt-4o");
    expect(payload.temperature).toBe(0.7);
    expect(payload.max_tokens).toBe(1024);
    expect(payload.top_p).toBe(1);
    expect(payload.knowledge_base_ids).toEqual([]);
    expect(payload.enabled_tool_ids).toEqual([]);
    // create payload must not carry `status`
    expect(payload).not.toHaveProperty("status");
  });

  it("reflects capability toggles and memory in the payload", async () => {
    const onSubmit = vi.fn();
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Toggle Agent" },
    });
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Hi." },
    });

    // defaults: function_calling off, multi_agent off, streaming on, memory on
    fireEvent.click(
      screen.getByRole("switch", { name: "Function Calling" }),
    );
    fireEvent.click(
      screen.getByRole("switch", { name: "Conversation Memory" }),
    );

    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());

    const payload = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.function_calling).toBe(true);
    expect(payload.multi_agent_routing).toBe(false);
    expect(payload.streaming).toBe(true);
    expect(payload.memory_enabled).toBe(false);
  });

  it("assigns knowledge bases and tools", async () => {
    const onSubmit = vi.fn();
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Assigned Agent" },
    });
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Hi." },
    });

    fireEvent.click(screen.getByRole("checkbox", { name: "Docs KB" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Web Search" }));

    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());

    const payload = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.knowledge_base_ids).toEqual(["kb1"]);
    expect(payload.enabled_tool_ids).toEqual(["t1"]);
  });

  it("updates the displayed temperature value from the slider", () => {
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Temperature"), {
      target: { value: "1.3" },
    });
    expect(screen.getByText("1.3")).toBeInTheDocument();
  });

  it("resets the model list when the provider changes", () => {
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "anthropic" },
    });
    const modelSelect = screen.getByLabelText("Model") as HTMLSelectElement;
    expect(modelSelect.value).toBe("claude-opus-4");
    expect(
      screen.getByRole("option", { name: "Claude Sonnet 4" }),
    ).toBeInTheDocument();
  });

  it("prefills fields and submits an update payload with status", async () => {
    const onSubmit = vi.fn();
    render(
      <AgentBuilderFormDialog
        open
        onOpenChange={vi.fn()}
        initial={detailFixture}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByLabelText("Name")).toHaveValue("Support Agent");
    expect(screen.getByLabelText("System prompt")).toHaveValue(
      "You are helpful.",
    );
    expect(screen.getByLabelText("Max tokens")).toHaveValue(2048);

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());

    const payload = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.name).toBe("Support Agent");
    expect(payload.status).toBe("active");
    expect(payload.knowledge_base_ids).toEqual(["kb1"]);
    expect(payload.enabled_tool_ids).toEqual(["t1"]);
  });

  it("surfaces an inline error when the submit rejects", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("Save failed"));
    render(
      <AgentBuilderFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Err Agent" },
    });
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Hi." },
    });
    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    expect(await screen.findByText("Save failed")).toBeInTheDocument();
  });

  it("disables inputs while submitting", () => {
    render(
      <AgentBuilderFormDialog
        open
        onOpenChange={vi.fn()}
        onSubmit={vi.fn()}
        isSubmitting
      />,
    );
    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /create agent/i }),
    ).toBeDisabled();
  });
});
