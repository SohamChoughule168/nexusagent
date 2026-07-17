import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentList } from "@/features/agent-builder/components/AgentList";
import type { AgentDetail } from "@/features/agent-builder/types";

const agents: AgentDetail[] = [
  {
    id: "a1",
    public_id: "pub1",
    name: "Alpha",
    description: "first",
    system_prompt: "sp",
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
  },
  {
    id: "a2",
    public_id: "pub2",
    name: "Beta",
    description: "second",
    system_prompt: "sp2",
    welcome_message: null,
    model_provider: "anthropic",
    model_name: "claude-opus-4",
    temperature: 0.5,
    max_tokens: 2048,
    top_p: 0.9,
    function_calling: true,
    multi_agent_routing: false,
    streaming: true,
    memory_enabled: true,
    status: "inactive",
    config: null,
    knowledge_base_ids: [],
    enabled_tool_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    has_changes: false,
  },
];

describe("AgentList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a card for every agent", () => {
    render(
      <AgentList
        agents={agents}
        onEdit={vi.fn()}
        onView={vi.fn()}
        onDelete={vi.fn()}
        onDuplicate={vi.fn()}
      />,
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("fires onView when a card's View Details is clicked", () => {
    const onView = vi.fn();
    render(
      <AgentList
        agents={agents}
        onEdit={vi.fn()}
        onView={onView}
        onDelete={vi.fn()}
        onDuplicate={vi.fn()}
      />,
    );
    const menus = screen.getAllByRole("button", { name: /open agent menu/i });
    fireEvent.click(menus[0]);
    fireEvent.click(screen.getByText("View Details"));
    expect(onView).toHaveBeenCalledTimes(1);
  });
});
