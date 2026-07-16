import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";
import { env } from "@/lib/env";
import { tokenStorage } from "@/lib/token-storage";
import { ApiError, type ApiErrorDetail } from "@/lib/api-error";

/**
 * Axios instance shared by every service. Responsibilities:
 *  - attach `Authorization: Bearer <access_token>` to outgoing requests
 *  - on 401, attempt a single token refresh and retry the original request
 *  - normalize every failure into a typed `ApiError`
 *
 * The backend exposes auth at `/api/v1/auth/*` and the refresh endpoint at
 * `/api/v1/auth/refresh` (JSON `{ refresh_token }`).
 */

const apiClient: AxiosInstance = axios.create({
  baseURL: env.apiBaseUrl,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000,
});

// ---- Request interceptor: attach access token --------------------------------

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

// ---- Refresh handling (single in-flight refresh, queue retries) --------------

let refreshPromise: Promise<string> | null = null;

function doRefresh(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) {
      throw new ApiError("UNAUTHORIZED", "No refresh token available");
    }

    // Bypass interceptors to avoid recursion: use a bare axios call.
    const { data } = await axios.post(`${env.apiBaseUrl}/auth/refresh`, {
      refresh_token: refreshToken,
    });

    tokenStorage.setTokens(data.access_token, data.refresh_token);
    if (data.user) tokenStorage.setUser(data.user);
    return data.access_token as string;
  })().finally(() => {
    // Reset so a later expiry can refresh again.
    refreshPromise = null;
  });

  return refreshPromise;
}

// ---- Response interceptor: error normalization + refresh retry --------------

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;

    // Network / timeout errors (no response) — wrap and surface.
    if (!error.response) {
      const code =
        error.code === "ECONNABORTED" || error.code === "ETIMEDOUT"
          ? "TIMEOUT"
          : "NETWORK";
      return Promise.reject(
        new ApiError(code, error.message || "Network error"),
      );
    }

    const status = error.response.status;

    // Only attempt refresh on 401, and never for the refresh call itself.
    const isRefreshCall = originalRequest?.url?.includes("/auth/refresh");
    if (status === 401 && !originalRequest?._retry && !isRefreshCall) {
      originalRequest!._retry = true;

      try {
        const token = await doRefresh();
        originalRequest!.headers.set("Authorization", `Bearer ${token}`);
        return apiClient(originalRequest!);
      } catch (refreshError) {
        tokenStorage.clear();
        return Promise.reject(
          refreshError instanceof ApiError
            ? refreshError
            : new ApiError("UNAUTHORIZED", "Session expired. Please sign in again."),
        );
      }
    }

    return Promise.reject(mapAxiosError(error));
  },
);

/** Map an Axios error to a typed ApiError with parsed backend detail. */
export function mapAxiosError(error: AxiosError): ApiError {
  const status = error.response?.status;
  const data = error.response?.data as
    | { detail?: unknown; message?: string }
    | undefined;

  let code: ApiError["code"] = "UNKNOWN";
  if (status === 401) code = "UNAUTHORIZED";
  else if (status === 403) code = "FORBIDDEN";
  else if (status === 404) code = "NOT_FOUND";
  else if (status === 422) code = "VALIDATION";
  else if (status && status >= 500) code = "SERVER";

  const details = parseDetails(data?.detail);
  const message = extractMessage(data, details, status);
  return new ApiError(code, message, status, details);
}

function parseDetails(detail: unknown): ApiErrorDetail[] {
  if (typeof detail === "string") return [{ message: detail }];
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (typeof d === "string") return { message: d };
      const obj = d as {
        loc?: (string | number)[];
        msg?: string;
        message?: string;
      };
      const field =
        Array.isArray(obj.loc) && obj.loc.length > 1
          ? String(obj.loc[obj.loc.length - 1])
          : undefined;
      return { field, message: obj.msg ?? obj.message ?? "Invalid value" };
    });
  }
  return [];
}

function extractMessage(
  data: { detail?: unknown; message?: string } | undefined,
  details: ApiErrorDetail[],
  status?: number,
): string {
  if (data?.message) return data.message;
  if (typeof data?.detail === "string") return data.detail;
  if (details.length > 0) return details[0].message;
  if (status && status >= 500) return "A server error occurred. Please try again.";
  return "Request failed";
}

/** Perform a request using the shared client. */
export function request<T>(config: AxiosRequestConfig): Promise<T> {
  return apiClient.request<unknown, T>(config);
}

export default apiClient;
