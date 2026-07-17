import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConversationItem } from "@/components/chat/conversation-item";
import type { Agent, Conversation } from "@/types/conversation";

const agent: Agent = {
  id: "a1",
  public_id: "pub1",
  name: "Support Bot",
  description: null,
  system_prompt: "",
  welcome_message: null,
  model_provider: "openrouter",
  model_name: "anthropic/claude",
  temperature: 0.7,
  max_tokens: 1024,
  top_p: 1,
  function_calling: false,
  multi_agent_routing: false,
  streaming: true,
  memory_enabled: true,
  status: "active",
  config: null,
  knowledge_base_ids: null,
  enabled_tool_ids: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

const conversation: Conversation = {
  id: "c1",
  organization_id: "o1",
  agent_id: "a1",
  session_id: "s1",
  user_identifier: null,
  user_metadata: null,
  summary: "Onboarding Q&A",
  message_count: 3,
  total_tokens: 120,
  total_cost_usd: 0.01,
  started_at: "2026-01-01T00:00:00Z",
  closed_at: null,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  messages: [],
};

describe("ConversationItem", () => {
  it("renders the title, agent and meta", () => {
    render(
      <ConversationItem
        conversation={conversation}
        agent={agent}
        isActive={false}
        onSelect={() => {}}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("Onboarding Q&A")).toBeInTheDocument();
    expect(screen.getByText(/Support Bot/)).toBeInTheDocument();
    expect(screen.getByText(/3 msgs/)).toBeInTheDocument();
  });

  it("falls back to the agent name when no summary is set", () => {
    render(
      <ConversationItem
        conversation={{ ...conversation, summary: null }}
        agent={agent}
        isActive={false}
        onSelect={() => {}}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("Support Bot")).toBeInTheDocument();
  });

  it("calls onSelect, onRename and onDelete", () => {
    const onSelect = vi.fn();
    const onRename = vi.fn();
    const onDelete = vi.fn();
    render(
      <ConversationItem
        conversation={conversation}
        agent={agent}
        isActive={false}
        onSelect={onSelect}
        onRename={onRename}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByText("Onboarding Q&A"));
    expect(onSelect).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Rename conversation"));
    expect(onRename).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Delete conversation"));
    expect(onDelete).toHaveBeenCalled();
  });

  it("marks the active conversation with aria-current", () => {
    render(
      <ConversationItem
        conversation={conversation}
        agent={agent}
        isActive
        onSelect={() => {}}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(
      screen.getByText("Onboarding Q&A").closest("button"),
    ).toHaveAttribute("aria-current", "true");
  });
});
