import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as nav from "next/navigation";
import { TopNav } from "@/components/layout/top-nav";
import { ThemeProvider } from "@/providers/theme-provider";
import { useAuthStore } from "@/store/auth.store";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ replace: vi.fn(), push: vi.fn() })),
}));

const replaceMock = vi.fn();

beforeEach(() => {
  replaceMock.mockReset();
  vi.mocked(nav.useRouter).mockReturnValue({
    replace: replaceMock,
    push: vi.fn(),
  } as any);
  useAuthStore.setState({
    user: {
      id: "1",
      email: "user@example.com",
      full_name: "Test User",
      organization_id: "o1",
      organization_name: "Acme",
      role: "owner",
    },
    accessToken: "a",
    refreshToken: "r",
    isAuthenticated: true,
    isLoading: false,
    error: null,
    hasHydrated: true,
  });
});

function renderTopNav() {
  return render(
    <ThemeProvider>
      <TopNav />
    </ThemeProvider>,
  );
}

describe("TopNav (layout)", () => {
  it("shows the organization name and user email", () => {
    renderTopNav();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("logs the user out and redirects to /login", async () => {
    renderTopNav();
    fireEvent.click(screen.getByLabelText("Sign out"));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("offers a theme toggle", () => {
    renderTopNav();
    expect(
      screen.getByRole("button", { name: /switch to (light|dark) mode/i }),
    ).toBeInTheDocument();
  });
});
