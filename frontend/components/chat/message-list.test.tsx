import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageList } from "@/components/chat/message-list";
import { useChatStore } from "@/store/chat.store";
import type { Message } from "@/types/conversation";

const messages: Message[] = [
  {
    id: "1",
    conversation_id: "c",
    organization_id: "o",
    role: "user",
    content: "Hi there",
    token_count: 1,
    citations: null,
    tool_calls: null,
    tool_results: null,
    model_provider: null,
    model_name: null,
    cost_usd: 0,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "2",
    conversation_id: "c",
    organization_id: "o",
    role: "assistant",
    content: "Hello **world**",
    token_count: 2,
    citations: {
      sources: [
        {
          chunk_id: "x",
          document_id: "d",
          score: 0.8,
          snippet: "snip text",
        },
      ],
    },
    tool_calls: null,
    tool_results: null,
    model_provider: "openrouter",
    model_name: "anthropic/claude",
    cost_usd: 0.001,
    created_at: "2026-01-01T00:00:05Z",
  },
];

describe("MessageList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      selectedConversationId: null,
      isStreaming: false,
      streamingText: "",
      streamError: null,
    });
  });

  it("renders user + assistant messages, citations and token usage", () => {
    useChatStore.setState({ isStreaming: false });
    const { container } = render(
      <MessageList messages={messages} isLoading={false} onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Hi there")).toBeInTheDocument();
    expect(container.textContent).toContain("Hello world");
    expect(screen.getByText("snip text")).toBeInTheDocument();
    expect(screen.getByText("2 tok")).toBeInTheDocument();
  });

  it("renders the in-flight streaming message", () => {
    useChatStore.setState({ isStreaming: true, streamingText: "Thinking…" });
    render(
      <MessageList messages={messages} isLoading={false} onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("shows a retry button on the last assistant message", () => {
    const onRetry = vi.fn();
    render(
      <MessageList messages={messages} isLoading={false} onRetry={onRetry} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledWith("Hi there");
  });

  it("surfaces a stream error banner", () => {
    useChatStore.setState({ streamError: "Generation failed" });
    render(
      <MessageList messages={messages} isLoading={false} onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Generation failed")).toBeInTheDocument();
  });
});
