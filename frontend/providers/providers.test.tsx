import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AppProviders } from "@/app/providers";
import { QueryProvider } from "@/providers/query-provider";
import { AuthProvider } from "@/providers/auth-provider";
import { useAuthStore } from "@/store/auth.store";

describe("providers", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      hasHydrated: false,
    });
  });

  it("AppProviders renders its children", () => {
    render(
      <AppProviders>
        <span>provider-child</span>
      </AppProviders>,
    );
    expect(screen.getByText("provider-child")).toBeInTheDocument();
  });

  it("QueryProvider renders children", () => {
    render(
      <QueryProvider>
        <span>query-child</span>
      </QueryProvider>,
    );
    expect(screen.getByText("query-child")).toBeInTheDocument();
  });

  it("AuthProvider rehydrates the session from storage on mount", async () => {
    const spy = vi.spyOn(useAuthStore.getState(), "rehydrate");
    // ensure a fresh spy (rehydrate is recreated by setState above)
    useAuthStore.setState({ hasHydrated: false });

    render(
      <AuthProvider>
        <span>auth-child</span>
      </AuthProvider>,
    );

    await waitFor(() => expect(useAuthStore.getState().hasHydrated).toBe(true));
    expect(screen.getByText("auth-child")).toBeInTheDocument();
    spy.mockRestore();
  });
});
