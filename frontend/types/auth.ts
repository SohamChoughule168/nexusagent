/**
 * Shared domain types mirroring the backend auth schemas.
 * Kept in sync with backend/app/schemas/auth.py so the frontend never
 * reimplements backend validation.
 */

/** Authenticated user as returned by the backend token responses. */
export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  organization_id: string;
  organization_name: string;
  role: string;
}

/** Token response from /auth/login, /auth/register, /auth/refresh. */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
}

/** Request body for /auth/login (OAuth2PasswordRequestForm: form-encoded). */
export interface LoginCredentials {
  email: string;
  password: string;
}

/** Request body for /auth/register. */
export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string | null;
  organization_name: string;
  organization_slug: string;
}

/** Request body for /auth/refresh. */
export interface RefreshPayload {
  refresh_token: string;
}

/** Request body for /auth/change-password.
 *
 * The target user is derived from the active Bearer session — only the current
 * and new passwords are sent (the backend no longer accepts `email`).
 */
export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}
