import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { KnowledgeBaseTable } from "@/features/knowledge-base/components/knowledge-base-table";
import type { KnowledgeBase } from "@/types/knowledge-base";

const kbs: KnowledgeBase[] = [
  {
    id: "kb1",
    organization_id: "o1",
    name: "Product Docs",
    description: "Help center articles",
    embedding_model: "text-embedding-3-small",
    chunk_size: 1000,
    chunk_overlap: 200,
    chunk_strategy: "recursive",
    retrieval_config: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-02-01T00:00:00Z",
  },
  {
    id: "kb2",
    organization_id: "o1",
    name: "Legal",
    description: null,
    embedding_model: "text-embedding-3-large",
    chunk_size: 800,
    chunk_overlap: 100,
    chunk_strategy: "fixed",
    retrieval_config: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  },
];

describe("KnowledgeBaseTable", () => {
  it("renders each knowledge base with its link and config", () => {
    render(<KnowledgeBaseTable knowledgeBases={kbs} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("Product Docs")).toBeInTheDocument();
    expect(screen.getByText("Legal")).toBeInTheDocument();
    const link = screen.getByText("Product Docs").closest("a");
    expect(link).toHaveAttribute("href", "/knowledge-bases/kb1");
    expect(screen.getByText("Help center articles")).toBeInTheDocument();
    expect(screen.getAllByText("recursive").length).toBeGreaterThan(0);
    expect(screen.getAllByText("fixed").length).toBeGreaterThan(0);
  });

  it("fires onEdit / onDelete for the matching row", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<KnowledgeBaseTable knowledgeBases={kbs} onEdit={onEdit} onDelete={onDelete} />);

    fireEvent.click(screen.getByLabelText("Edit Product Docs"));
    expect(onEdit).toHaveBeenCalledWith(kbs[0]);

    fireEvent.click(screen.getByLabelText("Delete Product Docs"));
    expect(onDelete).toHaveBeenCalledWith(kbs[0]);
  });

  it("renders a placeholder dash for a missing description", () => {
    render(<KnowledgeBaseTable knowledgeBases={kbs} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
