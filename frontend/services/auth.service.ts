import apiClient from "@/lib/api-client";
import type {
  LoginCredentials,
  PasswordChangePayload,
  RegisterPayload,
  TokenResponse,
} from "@/types/auth";

/**
 * Auth service — the single place that talks to the backend `/auth/*`
 * endpoints. Reuses backend validation (the backend owns schema rules);
 * this layer only shapes requests/responses.
 *
 * IMPORTANT: `/auth/login` expects an OAuth2 password form
 * (`application/x-www-form-urlencoded` with `username`/`password`), not JSON —
 * matching FastAPI's `OAuth2PasswordRequestForm` dependency in the backend.
 */

export const authService = {
  async login(credentials: LoginCredentials): Promise<TokenResponse> {
    const body = new URLSearchParams();
    body.set("username", credentials.email);
    body.set("password", credentials.password);

    const { data } = await apiClient.post<TokenResponse>("/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },

  async register(payload: RegisterPayload): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>(
      "/auth/register",
      payload,
    );
    return data;
  },

  async refresh(refreshToken: string): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>("/auth/refresh", {
      refresh_token: refreshToken,
    });
    return data;
  },

  async changePassword(payload: PasswordChangePayload): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>(
      "/auth/change-password",
      payload,
    );
    return data;
  },
};

export default authService;
