import { create } from "zustand";

/**
 * Toast / notification UI state (Zustand). This is purely client-side UI
 * state (server data lives in React Query). Components fire `success` /
 * `error` / `info` toasts from mutations; the `<Toaster />` renders them.
 */
export type ToastType = "success" | "error" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface NotificationState {
  toasts: Toast[];
  /** Push a toast; returns its id so callers can dismiss early if needed. */
  addToast: (toast: Omit<Toast, "id">) => string;
  removeToast: (id: string) => void;
  clear: () => void;
  /** Convenience helpers. */
  success: (title: string, message?: string) => string;
  error: (title: string, message?: string) => string;
  info: (title: string, message?: string) => string;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `toast-${counter}`;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  toasts: [],

  addToast: (toast) => {
    const id = nextId();
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    return id;
  },

  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  clear: () => set({ toasts: [] }),

  success: (title, message) => {
    const id = nextId();
    set((s) => ({
      toasts: [...s.toasts, { id, type: "success", title, message }],
    }));
    return id;
  },

  error: (title, message) => {
    const id = nextId();
    set((s) => ({
      toasts: [...s.toasts, { id, type: "error", title, message }],
    }));
    return id;
  },

  info: (title, message) => {
    const id = nextId();
    set((s) => ({
      toasts: [...s.toasts, { id, type: "info", title, message }],
    }));
    return id;
  },
}));

export default useNotificationStore;
