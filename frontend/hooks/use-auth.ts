"use client";

import { useAuthStore, type AuthState } from "@/store/auth.store";

/**
 * Convenience hook for reading/interacting with the auth slice.
 * Returns the full Zustand auth state (user, tokens, login, logout, ...).
 *
 * The store is the source of truth; `AuthProvider` handles rehydration.
 */
export function useAuth(): AuthState {
  return useAuthStore();
}

export default useAuth;
