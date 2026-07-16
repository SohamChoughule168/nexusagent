import { STORAGE_KEYS } from "@/lib/env";
import type { AuthUser } from "@/types/auth";

/**
 * Thin wrapper around localStorage for auth artifacts. Centralized so the
 * Axios interceptors (token refresh) and the Zustand auth store stay in sync
 * without importing each other.
 *
 * SSR-safe: all access is guarded so that server renders do not crash.
 */

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function read(key: string): string | null {
  if (!isBrowser()) return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Quota / privacy mode — ignore; session simply won't persist.
  }
}

function remove(key: string): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export const tokenStorage = {
  getAccessToken(): string | null {
    return read(STORAGE_KEYS.accessToken);
  },
  getRefreshToken(): string | null {
    return read(STORAGE_KEYS.refreshToken);
  },
  getUser(): AuthUser | null {
    const raw = read(STORAGE_KEYS.user);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  },
  setTokens(accessToken: string, refreshToken: string): void {
    write(STORAGE_KEYS.accessToken, accessToken);
    write(STORAGE_KEYS.refreshToken, refreshToken);
  },
  setUser(user: AuthUser): void {
    write(STORAGE_KEYS.user, JSON.stringify(user));
  },
  clear(): void {
    remove(STORAGE_KEYS.accessToken);
    remove(STORAGE_KEYS.refreshToken);
    remove(STORAGE_KEYS.user);
  },
};
