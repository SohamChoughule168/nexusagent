import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import * as nav from "next/navigation";
import { AuthGuard } from "@/features/auth/components/auth-guard";
import { useAuthStore } from "@/store/auth.store";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ replace: vi.fn(), push: vi.fn() })),
  usePathname: vi.fn(() => "/dashboard"),
  useSearchParams: vi.fn(() => ({ get: () => null })),
}));

const replaceMock = vi.fn();

beforeEach(() => {
  replaceMock.mockReset();
  vi.mocked(nav.useRouter).mockReturnValue({
    replace: replaceMock,
    push: vi.fn(),
  } as any);
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

describe("AuthGuard (protected routes)", () => {
  it("redirects unauthenticated users to /login with a redirect target", async () => {
    useAuthStore.setState({ hasHydrated: true, isAuthenticated: false });

    render(
      <AuthGuard>
        <div>Secret content</div>
      </AuthGuard>,
    );

    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith(
        "/login?redirect=%2Fdashboard",
      ),
    );
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });

  it("renders children for authenticated users", () => {
    useAuthStore.setState({ hasHydrated: true, isAuthenticated: true });

    render(
      <AuthGuard>
        <div>Secret content</div>
      </AuthGuard>,
    );

    expect(screen.getByText("Secret content")).toBeInTheDocument();
  });
});
