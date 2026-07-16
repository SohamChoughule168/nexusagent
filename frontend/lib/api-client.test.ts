import { describe, it, expect, vi, beforeEach } from "vitest";
import { AxiosError } from "axios";
import apiClient from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";

// Control the access token read by the request interceptor.
vi.mock("@/lib/token-storage", () => ({
  tokenStorage: {
    getAccessToken: vi.fn(() => "access-token"),
    getRefreshToken: vi.fn(() => "refresh-token"),
    getUser: vi.fn(() => null),
    setTokens: vi.fn(),
    setUser: vi.fn(),
    clear: vi.fn(),
  },
}));

// A mock axios adapter lets us inspect the final request config and simulate
// responses/errors without a network.
const mockAdapter = vi.fn();

beforeEach(() => {
  mockAdapter.mockReset();
  mockAdapter.mockImplementation(async (config: any) => ({
    data: { ok: true },
    status: 200,
    statusText: "OK",
    headers: {},
    config,
  }));
  apiClient.defaults.adapter = mockAdapter as any;
});

describe("api-client request interceptor", () => {
  it("attaches the Bearer Authorization header from storage", async () => {
    await apiClient.get("/me");
    const cfg = mockAdapter.mock.calls[0][0];
    expect(cfg.headers.get("Authorization")).toBe("Bearer access-token");
  });
});

describe("api-client response/error handling", () => {
  it("normalizes a 422 validation error into ApiError with parsed details", async () => {
    const err = new AxiosError(
      "bad",
      "GET",
      {} as any,
      {},
      {
        status: 422,
        statusText: "Unprocessable Entity",
        headers: {},
        data: {
          detail: [{ loc: ["body", "email"], msg: "invalid email" }],
        },
      } as any,
    );
    mockAdapter.mockRejectedValueOnce(err);

    const thrown = await apiClient.get("/x").catch((e) => e);
    expect(thrown).toBeInstanceOf(ApiError);
    expect((thrown as ApiError).code).toBe("VALIDATION");
    expect((thrown as ApiError).details[0].message).toBe("invalid email");
  });

  it("classifies a network/timeout error (no response) as TIMEOUT", async () => {
    const netErr = new AxiosError(
      "Network Error",
      "ECONNABORTED",
      undefined,
      undefined,
      undefined,
    );
    mockAdapter.mockRejectedValueOnce(netErr);

    const thrown = await apiClient.get("/n").catch((e) => e);
    expect((thrown as ApiError).code).toBe("TIMEOUT");
  });

  it("classifies a 5xx error as SERVER", async () => {
    const serverErr = new AxiosError(
      "fail",
      "GET",
      {} as any,
      {},
      {
        status: 500,
        statusText: "Internal Server Error",
        headers: {},
        data: { detail: "boom" },
      } as any,
    );
    mockAdapter.mockRejectedValueOnce(serverErr);

    const thrown = await apiClient.get("/s").catch((e) => e);
    expect((thrown as ApiError).code).toBe("SERVER");
  });
});
