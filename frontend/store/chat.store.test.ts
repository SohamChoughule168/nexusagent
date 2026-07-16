import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/store/chat.store";

const initial = {
  selectedConversationId: null,
  isStreaming: false,
  streamingText: "",
  streamError: null,
};

describe("chat store (UI state)", () => {
  beforeEach(() => {
    useChatStore.setState(initial);
  });

  it("selects a conversation and clears streaming state", () => {
    useChatStore.setState({
      isStreaming: true,
      streamingText: "partial",
      streamError: "boom",
    });
    useChatStore.getState().selectConversation("c1");
    expect(useChatStore.getState().selectedConversationId).toBe("c1");
    expect(useChatStore.getState().streamingText).toBe("");
    expect(useChatStore.getState().streamError).toBeNull();
  });

  it("accumulates streaming text and clears on start/finish", () => {
    useChatStore.getState().startStreaming();
    expect(useChatStore.getState().isStreaming).toBe(true);

    useChatStore.getState().appendStreamingText("Hello");
    useChatStore.getState().appendStreamingText(" world");
    expect(useChatStore.getState().streamingText).toBe("Hello world");

    useChatStore.getState().finishStreaming();
    expect(useChatStore.getState().isStreaming).toBe(false);
    // text kept until next start/full reset
    expect(useChatStore.getState().streamingText).toBe("Hello world");

    useChatStore.getState().resetStreaming();
    expect(useChatStore.getState().streamingText).toBe("");
    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().streamError).toBeNull();
  });

  it("records stream errors", () => {
    useChatStore.getState().setStreamError("failed");
    expect(useChatStore.getState().streamError).toBe("failed");
    useChatStore.getState().setStreamError(null);
    expect(useChatStore.getState().streamError).toBeNull();
  });
});
