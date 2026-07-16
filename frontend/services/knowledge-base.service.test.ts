import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "@/lib/api-client";
import { knowledgeBaseService } from "@/services/knowledge-base.service";

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

// A mock axios adapter lets us inspect the final request config without a network.
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

function lastConfig() {
  return mockAdapter.mock.calls[mockAdapter.mock.calls.length - 1][0];
}

describe("knowledgeBaseService", () => {
  it("lists knowledge bases with the correct path", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: [
        { id: "kb1", name: "Docs" },
        { id: "kb2", name: "Manuals" },
      ],
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    } as any);
    const kbs = await knowledgeBaseService.listKnowledgeBases();
    expect(kbs).toHaveLength(2);
    expect(lastConfig().method).toBe("get");
    expect(lastConfig().url).toBe("/knowledge-bases/");
  });

  it("creates a knowledge base with a JSON body", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: { id: "kb1", name: "Docs" },
      status: 201,
      statusText: "Created",
      headers: {},
      config: {},
    } as any);
    await knowledgeBaseService.createKnowledgeBase({
      name: "Docs",
      embedding_model: "text-embedding-3-small",
    });
    expect(lastConfig().method).toBe("post");
    expect(lastConfig().url).toBe("/knowledge-bases/");
    expect(lastConfig().data).toContain("Docs");
  });

  it("updates a knowledge base with PUT", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: { id: "kb1", name: "Renamed" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    } as any);
    await knowledgeBaseService.updateKnowledgeBase("kb1", { name: "Renamed" });
    expect(lastConfig().method).toBe("put");
    expect(lastConfig().url).toBe("/knowledge-bases/kb1");
  });

  it("deletes a knowledge base", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: {},
      status: 204,
      statusText: "No Content",
      headers: {},
      config: {},
    } as any);
    await knowledgeBaseService.deleteKnowledgeBase("kb1");
    expect(lastConfig().method).toBe("delete");
    expect(lastConfig().url).toBe("/knowledge-bases/kb1");
  });

  it("lists documents with the nested path", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: [{ id: "d1" }],
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    } as any);
    const docs = await knowledgeBaseService.listDocuments("kb1");
    expect(docs).toHaveLength(1);
    expect(lastConfig().url).toBe("/knowledge-bases/kb1/documents");
  });

  it("uploads a document as multipart/form-data and reports progress", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: { id: "d1", filename: "a.pdf", status: "uploaded" },
      status: 201,
      statusText: "Created",
      headers: {},
      config: {},
    } as any);
    const file = new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });
    const onProgress = vi.fn();
    await knowledgeBaseService.uploadDocument("kb1", file, { onProgress });

    const cfg = lastConfig();
    expect(cfg.method).toBe("post");
    expect(cfg.url).toBe("/knowledge-bases/kb1/documents");
    expect(cfg.headers["Content-Type"]).toBe("multipart/form-data");
    // FormData body carries the file.
    expect(cfg.data).toBeInstanceOf(FormData);
    // A progress callback is wired up.
    expect(typeof cfg.onUploadProgress).toBe("function");
  });

  it("ingests and embeds a document at the right endpoints", async () => {
    mockAdapter.mockResolvedValueOnce({
      data: { id: "d1", status: "processed" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    } as any);
    mockAdapter.mockResolvedValueOnce({
      data: { id: "d1", status: "indexed" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    } as any);
    await knowledgeBaseService.ingestDocument("d1");
    expect(lastConfig().url).toBe("/documents/d1/ingest");
    await knowledgeBaseService.embedDocument("d1");
    expect(lastConfig().url).toBe("/documents/d1/embed");
  });
});
