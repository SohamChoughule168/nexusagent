import { create } from "zustand";
import { tokenStorage } from "@/lib/token-storage";
import { authService } from "@/services/auth.service";
import type { AuthUser, LoginCredentials, RegisterPayload } from "@/types/auth";

/**
 * Global auth state (Zustand). Holds the authenticated user and the tokens,
 * persisting them to localStorage via `tokenStorage`. Server state (data
 * fetched from the API) lives in React Query — this store is only for the
 * auth/session slice.
 *
 * Rehydration: on first client load we read whatever is already in
 * localStorage so a refresh keeps the user signed in.
 */

export interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  hasHydrated: boolean;

  login: (credentials: LoginCredentials) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  rehydrate: () => void;
}

function applyTokens(user: AuthUser, accessToken: string, refreshToken: string) {
  tokenStorage.setTokens(accessToken, refreshToken);
  tokenStorage.setUser(user);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  hasHydrated: false,

  login: async (credentials) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.login(credentials);
      applyTokens(res.user, res.access_token, res.refresh_token);
      set({
        user: res.user,
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Login failed",
      });
      throw err;
    }
  },

  register: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.register(payload);
      applyTokens(res.user, res.access_token, res.refresh_token);
      set({
        user: res.user,
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Registration failed",
      });
      throw err;
    }
  },

  logout: () => {
    tokenStorage.clear();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null,
    });
  },

  clearError: () => set({ error: null }),

  rehydrate: () => {
    if (get().isAuthenticated) {
      set({ hasHydrated: true });
      return;
    }
    const accessToken = tokenStorage.getAccessToken();
    const refreshToken = tokenStorage.getRefreshToken();
    const user = tokenStorage.getUser();
    if (accessToken && refreshToken && user) {
      set({
        accessToken,
        refreshToken,
        user,
        isAuthenticated: true,
        hasHydrated: true,
      });
    } else {
      set({ hasHydrated: true });
    }
  },
}));

export default useAuthStore;
