/**
 * Typed error surfaced from the API client. Wraps Axios errors so that
 * UI code can branch on machine-readable `code` / `status` instead of
 * parsing exception messages.
 */
import { useNotificationStore } from "@/store/notification.store";
export type ApiErrorCode =
  | "NETWORK"
  | "TIMEOUT"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION"
  | "SERVER"
  | "UNKNOWN";

export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly details: ApiErrorDetail[];

  constructor(
    code: ApiErrorCode,
    message: string,
    status?: number,
    details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/** Extract a human-readable message from an arbitrary Axios error. */
export function getErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred";
}

/** User-facing copy per error category — avoids leaking technical details. */
const FRIENDLY_MESSAGES: Record<ApiErrorCode, string> = {
  NETWORK: "We couldn't reach the server. Check your connection and try again.",
  TIMEOUT: "The request took too long. Please try again.",
  UNAUTHORIZED: "Your session has expired. Please sign in again.",
  FORBIDDEN: "You don't have permission to do that.",
  NOT_FOUND: "The requested resource was not found.",
  VALIDATION: "Please check the form and try again.",
  SERVER: "Something went wrong on our end. Please try again shortly.",
  UNKNOWN: "An unexpected error occurred. Please try again.",
};

/**
 * Surface an API error as a friendly toast. Maps the machine-readable code to
 * safe, user-facing copy and fires it through the notification store. Safe to
 * call from any client code (the store can be used outside React).
 */
export function notifyApiError(err: unknown): void {
  const code = err instanceof ApiError ? err.code : "UNKNOWN";
  const message = FRIENDLY_MESSAGES[code] ?? FRIENDLY_MESSAGES.UNKNOWN;
  useNotificationStore.getState().error("Request failed", message);
}
