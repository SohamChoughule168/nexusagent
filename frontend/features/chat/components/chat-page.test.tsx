import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const h = vi.hoisted(() => {
  const agent = {
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
  const conv = {
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
  const userMsg = {
    id: "m1",
    conversation_id: "c1",
    organization_id: "o1",
    role: "user",
    content: "Hi there",
    token_count: 2,
    citations: null,
    tool_calls: null,
    tool_results: null,
    model_provider: null,
    model_name: null,
    cost_usd: 0,
    created_at: "2026-01-01T00:00:00Z",
  };
  const asstMsg = {
    id: "m2",
    conversation_id: "c1",
    organization_id: "o1",
    role: "assistant",
    content: "Hello **world**",
    token_count: 2,
    citations: null,
    tool_calls: null,
    tool_results: null,
    model_provider: "openrouter",
    model_name: "anthropic/claude",
    cost_usd: 0.001,
    created_at: "2026-01-01T00:00:05Z",
  };
  return { agent, conv, userMsg, asstMsg };
});

const storeState = {
  selectedConversationId: "c1",
  isStreaming: false,
  streamingText: "",
  streamError: null,
  selectConversation: vi.fn(),
  resetStreaming: vi.fn(),
};

vi.mock("@/store/chat.store", () => ({
  useChatStore: (sel?: (s: typeof storeState) => unknown) =>
    sel ? sel(storeState) : storeState,
}));

vi.mock("@/hooks/use-conversations", () => ({
  useConversations: () => ({
    conversations: [h.conv],
    createConversationAsync: vi.fn().mockResolvedValue(h.conv),
    renameConversationAsync: vi.fn().mockResolvedValue(undefined),
    deleteConversationAsync: vi.fn().mockResolvedValue(undefined),
    isCreating: false,
  }),
}));

vi.mock("@/hooks/use-agents", () => ({
  useAgents: () => ({ agents: [h.agent], isLoading: false }),
}));

vi.mock("@/hooks/use-messages", () => ({
  useMessages: () => ({
    messages: [h.userMsg, h.asstMsg],
    isLoading: false,
    invalidate: vi.fn(),
    appendOptimistic: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-chat-stream", () => ({
  useChatStream: () => ({
    send: vi.fn(),
    stop: vi.fn(),
    isStreaming: false,
  }),
}));

import { ChatPage } from "@/features/chat/components/chat-page";

describe("ChatPage (module integration)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the conversation list and the open thread", () => {
    const { container } = render(<ChatPage />);
    // List pane
    expect(screen.getByText("Conversations")).toBeInTheDocument();
    expect(
      screen.getAllByText("Onboarding Q&A").length,
    ).toBeGreaterThan(0);
    // Thread pane (selected conversation)
    expect(
      screen.getAllByText(/Support Bot/).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Hi there")).toBeInTheDocument();
    expect(container.textContent).toContain("Hello world");
    // Composer
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
  });
});
