/**
 * Runtime environment configuration for the frontend.
 *
 * Reads public (NEXT_PUBLIC_*) variables injected at build time by Next.js.
 * Falls back to a sane local-dev default that matches the backend's
 * CORS allow-list (http://localhost:3000 -> http://localhost:8000).
 */
export const env = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "NexusAgent",
} as const;

/** Storage keys for auth tokens (shared between store and API client). */
export const STORAGE_KEYS = {
  accessToken: "nexusagent.access_token",
  refreshToken: "nexusagent.refresh_token",
  user: "nexusagent.user",
} as const;
