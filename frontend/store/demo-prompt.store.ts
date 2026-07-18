import { create } from "zustand";

/**
 * Demo-only signal used to push a "suggested prompt" from the marketing demo
 * page into the live chat composer. Always `null` in the real app, so the
 * shared chat components that read it are unaffected.
 */
interface DemoPromptState {
  pendingPrompt: string | null;
  setPendingPrompt: (prompt: string | null) => void;
}

export const useDemoPromptStore = create<DemoPromptState>((set) => ({
  pendingPrompt: null,
  setPendingPrompt: (prompt) => set({ pendingPrompt: prompt }),
}));

export default useDemoPromptStore;
