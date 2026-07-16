import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ConversationList } from "@/components/chat/conversation-list";
import type { Agent, Conversation } from "@/types/conversation";

const agent: Agent = {
  id: "a1",
  public_id: "pub1",
  name: "Support Bot",
  description: "Helps users",
  system_prompt: "",
  welcome_message: null,
  model_provider: "openrouter",
  model_name: "anthropic/claude",
  temperature: 0.7,
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
  message_count: 2,
  total_tokens: 50,
  total_cost_usd: 0.001,
  started_at: "2026-01-01T00:00:00Z",
  closed_at: null,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  messages: [],
};

function setup(overrides: Partial<Parameters<typeof ConversationList>[0]> = {}) {
  const onSelect = vi.fn();
  const onCreate = vi.fn();
  const onRename = vi.fn();
  const onDelete = vi.fn();
  const onNewOpenChange = vi.fn();
  const utils = render(
    <ConversationList
      conversations={[conversation]}
      agents={[agent]}
      isLoadingAgents={false}
      selectedId="c1"
      newOpen={false}
      onNewOpenChange={onNewOpenChange}
      onSelect={onSelect}
      onCreate={onCreate}
      onRename={onRename}
      onDelete={onDelete}
      {...overrides}
    />,
  );
  return { onSelect, onCreate, onRename, onDelete, onNewOpenChange, ...utils };
}

describe("ConversationList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders conversations and selects on click", () => {
    setup();
    expect(screen.getByText("Onboarding Q&A")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Onboarding Q&A"));
    expect(screen.getByText(/Support Bot/)).toBeInTheDocument();
  });

  it("shows an empty state with a New button", () => {
    const { onNewOpenChange } = setup({ conversations: [] });
    expect(screen.getByText("No conversations yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /new conversation/i }));
    expect(onNewOpenChange).toHaveBeenCalledWith(true);
  });

  it("opens the new-conversation dialog with agents", async () => {
    setup({ newOpen: true });
    expect(await screen.findByText("New conversation")).toBeInTheDocument();
    expect(screen.getByText("Support Bot")).toBeInTheDocument();
    // start chat disabled until an agent is picked
    expect(
      screen.getByRole("button", { name: /start chat/i }),
    ).toBeDisabled();
  });

  it("opens the rename dialog and saves", async () => {
    const { onRename } = setup();
    fireEvent.click(screen.getByLabelText("Rename conversation"));
    expect(await screen.findByText("Rename conversation")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onRename).toHaveBeenCalledWith("c1", "Renamed"));
  });

  it("opens the delete confirmation and deletes", async () => {
    const { onDelete } = setup();
    fireEvent.click(screen.getByLabelText("Delete conversation"));
    expect(await screen.findByText("Delete conversation?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith("c1"));
  });
});
