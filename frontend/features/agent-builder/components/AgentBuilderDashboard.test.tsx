import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { AgentDetail } from "@/features/agent-builder/types";

const h = vi.hoisted(() => {
  const agent: AgentDetail = {
    id: "a1",
    public_id: "pub1",
    name: "Support Agent",
    description: "Helps users",
    system_prompt: "Be helpful.",
    welcome_message: null,
    model_provider: "openai",
    model_name: "gpt-4o",
    temperature: 0.7,
    max_tokens: 1024,
    top_p: 1,
    function_calling: false,
    multi_agent_routing: false,
    streaming: true,
    memory_enabled: true,
    status: "active",
    config: null,
    knowledge_base_ids: [],
    enabled_tool_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    has_changes: false,
  };
  return {
    agent,
    createAsync: vi.fn().mockResolvedValue({ ...agent, id: "a2" }),
    updateAsync: vi.fn().mockResolvedValue(agent),
    deleteAsync: vi.fn().mockResolvedValue(undefined),
    duplicateAsync: vi.fn().mockResolvedValue({ ...agent, id: "a3" }),
    success: vi.fn(),
    error: vi.fn(),
    state: { isLoading: false, isError: false },
  };
});

vi.mock("@/features/agent-builder/hooks/use-agents", () => ({
  useAgents: () => ({
    data: h.state.isLoading || h.state.isError ? undefined : [h.agent],
    isLoading: h.state.isLoading,
    isError: h.state.isError,
    error: h.state.isError ? new Error("boom") : null,
    refetch: vi.fn(),
  }),
  useCreateAgent: () => ({ mutateAsync: h.createAsync, isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: h.updateAsync, isPending: false }),
  useDeleteAgent: () => ({ mutateAsync: h.deleteAsync, isPending: false }),
  useDuplicateAgent: () => ({ mutateAsync: h.duplicateAsync, isPending: false }),
  useTools: () => ({ data: [], isLoading: false }),
  useKnowledgeBases: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/store/notification.store", () => ({
  useNotificationStore: () => ({ success: h.success, error: h.error }),
}));

import { AgentBuilderDashboard } from "@/features/agent-builder/components/AgentBuilderDashboard";

describe("AgentBuilderDashboard (module integration)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.state.isLoading = false;
    h.state.isError = false;
  });

  it("lists agents from the query hook", () => {
    render(<AgentBuilderDashboard />);
    expect(
      screen.getByRole("heading", { name: "Agent Builder" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Support Agent")).toBeInTheDocument();
  });

  it("filters the list by the search box", () => {
    render(<AgentBuilderDashboard />);
    fireEvent.change(screen.getByLabelText("Search agents"), {
      target: { value: "zzz" },
    });
    expect(screen.getByText("No matches")).toBeInTheDocument();
    expect(screen.queryByText("Support Agent")).not.toBeInTheDocument();
  });

  it("shows the loading state", () => {
    h.state.isLoading = true;
    render(<AgentBuilderDashboard />);
    expect(screen.getByText("Loading agents...")).toBeInTheDocument();
  });

  it("shows the error state with a retry", () => {
    h.state.isError = true;
    render(<AgentBuilderDashboard />);
    expect(screen.getByText("Failed to load agents")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /retry/i }),
    ).toBeInTheDocument();
  });

  it("creates an agent and fires a success toast", async () => {
    render(<AgentBuilderDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /new agent/i }));

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Brand New" },
    });
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Hello." },
    });
    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    await waitFor(() => expect(h.createAsync).toHaveBeenCalledTimes(1));
    expect(h.success).toHaveBeenCalledWith("Agent created", "Brand New");
  });

  it("duplicates an agent from the card menu", async () => {
    render(<AgentBuilderDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("Duplicate"));
    await waitFor(() => expect(h.duplicateAsync).toHaveBeenCalledTimes(1));
    expect(h.success).toHaveBeenCalledWith("Agent duplicated", "Support Agent");
  });

  it("deletes an agent after confirmation", async () => {
    render(<AgentBuilderDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("Delete"));
    // Confirm dialog
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(h.deleteAsync).toHaveBeenCalledWith("a1"));
    expect(h.success).toHaveBeenCalledWith("Agent deleted", "Support Agent");
  });
});
