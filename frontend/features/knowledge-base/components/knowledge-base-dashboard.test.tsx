import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { KnowledgeBaseDashboard } from "@/features/knowledge-base/components/knowledge-base-dashboard";
import type { KnowledgeBase } from "@/types/knowledge-base";

vi.mock("@/hooks/use-knowledge-bases", () => ({
  useKnowledgeBases: vi.fn(),
}));

vi.mock("@/store/notification.store", () => ({
  useNotificationStore: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  })),
}));

import * as kbHook from "@/hooks/use-knowledge-bases";

const kbs: KnowledgeBase[] = [
  {
    id: "kb1",
    organization_id: "o1",
    name: "Product Docs",
    description: "Help center",
    embedding_model: "text-embedding-3-small",
    chunk_size: 1000,
    chunk_overlap: 200,
    chunk_strategy: "recursive",
    retrieval_config: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  },
  {
    id: "kb2",
    organization_id: "o1",
    name: "Legal",
    description: null,
    embedding_model: "text-embedding-3-small",
    chunk_size: 1000,
    chunk_overlap: 200,
    chunk_strategy: "recursive",
    retrieval_config: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  },
];

function mockHook(over: Record<string, unknown> = {}) {
  vi.mocked(kbHook.useKnowledgeBases).mockReturnValue({
    knowledgeBases: kbs,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    createKnowledgeBaseAsync: vi.fn().mockResolvedValue({ id: "kb3" }),
    updateKnowledgeBaseAsync: vi.fn().mockResolvedValue({}),
    isCreating: false,
    isUpdating: false,
    deleteKnowledgeBaseAsync: vi.fn().mockResolvedValue(undefined),
    isDeleting: false,
    ...over,
  } as any);
}

describe("KnowledgeBaseDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHook();
  });

  it("renders the heading, search, and new button", () => {
    render(<KnowledgeBaseDashboard />);
    expect(screen.getByText("Knowledge Bases")).toBeInTheDocument();
    expect(screen.getByLabelText("Search knowledge bases")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new knowledge base/i })).toBeInTheDocument();
  });

  it("renders the knowledge base list", () => {
    render(<KnowledgeBaseDashboard />);
    expect(screen.getByText("Product Docs")).toBeInTheDocument();
    expect(screen.getByText("Legal")).toBeInTheDocument();
  });

  it("filters the list by the search query", () => {
    render(<KnowledgeBaseDashboard />);
    fireEvent.change(screen.getByLabelText("Search knowledge bases"), {
      target: { value: "Legal" },
    });
    expect(screen.getByText("Legal")).toBeInTheDocument();
    expect(screen.queryByText("Product Docs")).not.toBeInTheDocument();
  });

  it("renders the empty state when there are no knowledge bases", () => {
    mockHook({ knowledgeBases: [] });
    render(<KnowledgeBaseDashboard />);
    expect(screen.getByText("No knowledge bases yet")).toBeInTheDocument();
  });

  it("renders a loading state", () => {
    mockHook({ isLoading: true });
    render(<KnowledgeBaseDashboard />);
    expect(screen.getByText("Loading knowledge bases...")).toBeInTheDocument();
  });

  it("renders an error state with a retry button", () => {
    const refetch = vi.fn();
    mockHook({ isError: true, error: new Error("boom"), refetch });
    render(<KnowledgeBaseDashboard />);
    expect(screen.getByText("Failed to load knowledge bases")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it("opens the create dialog and submits a new knowledge base", async () => {
    render(<KnowledgeBaseDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /new knowledge base/i }));

    const nameInput = await screen.findByLabelText("Name");
    fireEvent.change(nameInput, { target: { value: "Research" } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() =>
      expect(kbHook.useKnowledgeBases().createKnowledgeBaseAsync).toHaveBeenCalled(),
    );
    const payload = (kbHook.useKnowledgeBases().createKnowledgeBaseAsync as any).mock
      .calls[0][0];
    expect(payload.name).toBe("Research");
  });
});
