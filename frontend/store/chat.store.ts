import { create } from "zustand";

/**
 * Chat *UI* state (Zustand). Only transient, cross-cutting UI concerns live
 * here — server state (conversations, messages, agents) is owned by React
 * Query. The streaming text is intentionally ephemeral UI state: it is the
 * in-flight assistant reply shown before the backend persists the final message.
 */
export interface ChatUIState {
  /** Conversation currently open in the thread pane. */
  selectedConversationId: string | null;
  /** True while an assistant reply is streaming. */
  isStreaming: boolean;
  /** Accumulated assistant text during streaming. */
  streamingText: string;
  /** Error surfaced from a failed/aborted stream (non-abort). */
  streamError: string | null;

  selectConversation: (id: string | null) => void;
  startStreaming: () => void;
  appendStreamingText: (chunk: string) => void;
  finishStreaming: () => void;
  setStreamError: (msg: string | null) => void;
  resetStreaming: () => void;
}

export const useChatStore = create<ChatUIState>((set) => ({
  selectedConversationId: null,
  isStreaming: false,
  streamingText: "",
  streamError: null,

  selectConversation: (id) =>
    set({ selectedConversationId: id, streamingText: "", streamError: null }),

  startStreaming: () =>
    set({ isStreaming: true, streamingText: "", streamError: null }),

  appendStreamingText: (chunk) =>
    set((s) => ({ streamingText: s.streamingText + chunk })),

  finishStreaming: () => set({ isStreaming: false }),

  setStreamError: (msg) => set({ streamError: msg }),

  resetStreaming: () =>
    set({ isStreaming: false, streamingText: "", streamError: null }),
}));

export default useChatStore;
