import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { KnowledgeBaseFormDialog } from "@/features/knowledge-base/components/knowledge-base-form-dialog";
import type { KnowledgeBase } from "@/types/knowledge-base";

const kb: KnowledgeBase = {
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
  updated_at: null,
};

describe("KnowledgeBaseFormDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits a create payload with defaults", async () => {
    const onSubmit = vi.fn();
    render(<KnowledgeBaseFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "New KB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.name).toBe("New KB");
    expect(payload.embedding_model).toBe("text-embedding-3-small");
    expect(payload.chunk_strategy).toBe("recursive");
    expect(payload.chunk_size).toBe(1000);
    expect(payload.chunk_overlap).toBe(200);
  });

  it("does not submit when the name is blank", () => {
    const onSubmit = vi.fn();
    render(<KnowledgeBaseFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Name is required")).toBeInTheDocument();
  });

  it("prefills fields in edit mode and shows 'Save changes'", () => {
    render(<KnowledgeBaseFormDialog open onOpenChange={vi.fn()} initial={kb} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText("Name")).toHaveValue("Product Docs");
    expect(screen.getByLabelText("Description")).toHaveValue("Help center articles");
    expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
  });

  it("captures custom chunk size / overlap values", async () => {
    const onSubmit = vi.fn();
    render(<KnowledgeBaseFormDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "KB" } });
    fireEvent.change(screen.getByLabelText("Chunk size (tokens)"), {
      target: { value: "500" },
    });
    fireEvent.change(screen.getByLabelText("Chunk overlap (tokens)"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.chunk_size).toBe(500);
    expect(payload.chunk_overlap).toBe(50);
  });
});
