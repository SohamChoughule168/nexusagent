import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentCard } from "@/features/agent-builder/components/AgentCard";
import type { AgentDetail } from "@/features/agent-builder/types";

function makeAgent(overrides: Partial<AgentDetail> = {}): AgentDetail {
  return {
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
    knowledge_base_ids: ["kb1"],
    enabled_tool_ids: ["t1", "t2"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    has_changes: false,
    ...overrides,
  };
}

describe("AgentCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders name, description, model and counts", () => {
    render(<AgentCard agent={makeAgent()} onEdit={vi.fn()} onView={vi.fn()} onDelete={vi.fn()} onDuplicate={vi.fn()} />);
    expect(screen.getByText("Support Agent")).toBeInTheDocument();
    expect(screen.getByText("Helps users")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument(); // KB count
    expect(screen.getByText("2")).toBeInTheDocument(); // tool count
  });

  it("shows an Active badge for active agents", () => {
    render(<AgentCard agent={makeAgent()} onEdit={vi.fn()} onView={vi.fn()} onDelete={vi.fn()} onDuplicate={vi.fn()} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows an Inactive badge for inactive agents", () => {
    render(<AgentCard agent={makeAgent({ status: "inactive" })} onEdit={vi.fn()} onView={vi.fn()} onDelete={vi.fn()} onDuplicate={vi.fn()} />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("opens the menu and fires callbacks", () => {
    const onEdit = vi.fn();
    const onView = vi.fn();
    const onDelete = vi.fn();
    const onDuplicate = vi.fn();
    render(
      <AgentCard
        agent={makeAgent()}
        onEdit={onEdit}
        onView={onView}
        onDelete={onDelete}
        onDuplicate={onDuplicate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("View Details"));
    expect(onView).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("Edit Agent"));
    expect(onEdit).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("Duplicate"));
    expect(onDuplicate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /open agent menu/i }));
    fireEvent.click(screen.getByText("Delete"));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("fires onEdit from the Configure button", () => {
    const onEdit = vi.fn();
    render(<AgentCard agent={makeAgent()} onEdit={onEdit} onView={vi.fn()} onDelete={vi.fn()} onDuplicate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /configure/i }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});
