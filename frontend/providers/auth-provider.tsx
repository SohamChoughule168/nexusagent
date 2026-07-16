"use client";

import {
  createContext,
  useContext,
  useEffect,
  type ReactNode,
} from "react";
import { useAuthStore, type AuthState } from "@/store/auth.store";

/**
 * Auth provider / context. Wraps the app so that the persisted session is
 * rehydrated from localStorage on first client mount, then exposes the Zustand
 * auth slice through React context for convenience (and testability).
 *
 * The Zustand store remains the source of truth; this provider only performs
 * the rehydration side-effect and surfaces the state via context.
 */

export type AuthContextValue = AuthState;

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Subscribe to the whole auth slice.
  const auth = useAuthStore();

  // Rehydrate on first client render (e.g. after a page refresh).
  useEffect(() => {
    useAuthStore.getState().rehydrate();
  }, []);

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
