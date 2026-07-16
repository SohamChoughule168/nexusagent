import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the auth service so the store never hits the network. The token storage
// is left real (jsdom provides localStorage) and we assert against it.
vi.mock("@/services/auth.service", () => ({
  authService: {
    login: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
    changePassword: vi.fn(),
  },
  default: {},
}));

import { useAuthStore } from "@/store/auth.store";
import { authService } from "@/services/auth.service";
import type { TokenResponse } from "@/types/auth";

const sampleToken: TokenResponse = {
  access_token: "a",
  refresh_token: "r",
  token_type: "bearer",
  user: {
    id: "1",
    email: "user@example.com",
    full_name: "Test User",
    organization_id: "o1",
    organization_name: "Acme",
    role: "owner",
  },
};

const initial = {
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  hasHydrated: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useAuthStore.setState(initial);
});

describe("auth store", () => {
  it("login persists the session and tokens on success", async () => {
    (authService.login as any).mockResolvedValueOnce(sampleToken);

    await useAuthStore.getState().login({ email: "user@example.com", password: "pw" });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.email).toBe("user@example.com");
    expect(localStorage.getItem("nexusagent.access_token")).toBe("a");
    expect(localStorage.getItem("nexusagent.refresh_token")).toBe("r");
    expect(localStorage.getItem("nexusagent.user")).toContain("user@example.com");
  });

  it("login records the error and throws on failure", async () => {
    (authService.login as any).mockRejectedValueOnce(new Error("bad creds"));

    await expect(
      useAuthStore.getState().login({ email: "x", password: "y" }),
    ).rejects.toThrow("bad creds");

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().error).toBe("bad creds");
  });

  it("logout clears session state and storage", () => {
    useAuthStore.setState({
      user: sampleToken.user,
      accessToken: "a",
      refreshToken: "r",
      isAuthenticated: true,
    });

    useAuthStore.getState().logout();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
    expect(localStorage.getItem("nexusagent.access_token")).toBeNull();
  });

  it("rehydrate restores a persisted session from storage", () => {
    localStorage.setItem("nexusagent.access_token", "a");
    localStorage.setItem("nexusagent.refresh_token", "r");
    localStorage.setItem("nexusagent.user", JSON.stringify(sampleToken.user));

    useAuthStore.getState().rehydrate();

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().hasHydrated).toBe(true);
  });

  it("rehydrate sets hasHydrated even when nothing is stored", () => {
    useAuthStore.getState().rehydrate();

    expect(useAuthStore.getState().hasHydrated).toBe(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
