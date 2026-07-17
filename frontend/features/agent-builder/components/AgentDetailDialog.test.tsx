import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentDetailDialog } from "@/features/agent-builder/components/AgentDetailDialog";
import type { AgentDetail } from "@/features/agent-builder/types";

const agent: AgentDetail = {
  id: "a1",
  public_id: "pub1",
  name: "Support Agent",
  description: "Helps users",
  system_prompt: "You are helpful.",
  welcome_message: "Hi!",
  model_provider: "openai",
  model_name: "gpt-4o",
  temperature: 0.7,
  max_tokens: 1024,
  top_p: 1,
  function_calling: true,
  multi_agent_routing: false,
  streaming: true,
  memory_enabled: true,
  status: "active",
  config: null,
  knowledge_base_ids: ["kb1"],
  enabled_tool_ids: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  has_changes: false,
};

describe("AgentDetailDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the agent's configuration when open", () => {
    render(
      <AgentDetailDialog
        open
        onOpenChange={vi.fn()}
        agent={agent}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.getByText("Support Agent")).toBeInTheDocument();
    expect(screen.getByText("openai / gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("You are helpful.")).toBeInTheDocument();
    expect(screen.getByText("Function Calling: On")).toBeInTheDocument();
    expect(screen.getByText("Memory: On")).toBeInTheDocument();
    expect(screen.getByText("0.7")).toBeInTheDocument();
    expect(screen.getByText("1024")).toBeInTheDocument();
  });

  it("calls onEdit then closes when Edit is clicked", () => {
    const onEdit = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <AgentDetailDialog
        open
        onOpenChange={onOpenChange}
        agent={agent}
        onEdit={onEdit}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("closes on the Close button", () => {
    const onOpenChange = vi.fn();
    render(
      <AgentDetailDialog
        open
        onOpenChange={onOpenChange}
        agent={agent}
        onEdit={vi.fn()}
      />,
    );
    // Footer "Close" button (Radix also renders an X with the label "Close").
    const closeButtons = screen.getAllByRole("button", { name: "Close" });
    fireEvent.click(closeButtons[0]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
