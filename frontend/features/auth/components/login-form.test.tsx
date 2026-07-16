import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as nav from "next/navigation";
import { LoginForm } from "@/features/auth/components/login-form";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/store/auth.store";

vi.mock("@/services/auth.service", () => ({
  authService: {
    login: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
    changePassword: vi.fn(),
  },
  default: {},
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ replace: vi.fn(), push: vi.fn() })),
  useSearchParams: vi.fn(() => ({ get: () => null })),
}));

const replaceMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
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

describe("LoginForm (authentication flow)", () => {
  it("submits credentials and redirects to the dashboard on success", async () => {
    (authService.login as any).mockResolvedValueOnce({
      access_token: "a",
      refresh_token: "r",
      token_type: "bearer",
      user: {
        id: "1",
        email: "user@example.com",
        full_name: "Test",
        organization_id: "o1",
        organization_name: "Acme",
        role: "owner",
      },
    });

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(authService.login).toHaveBeenCalledWith({
        email: "user@example.com",
        password: "secret123",
      }),
    );
    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith("/dashboard"),
    );
  });

  it("shows validation errors and does not call the API for empty fields", async () => {
    render(<LoginForm />);

    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Email is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(authService.login).not.toHaveBeenCalled();
  });

  it("surfaces an API error inline", async () => {
    (authService.login as any).mockRejectedValueOnce(
      new Error("Incorrect email or password"),
    );

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText("Incorrect email or password"),
    ).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
