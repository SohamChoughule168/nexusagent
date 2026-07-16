import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DocumentList } from "@/features/knowledge-base/components/document-list";
import type { Document } from "@/types/knowledge-base";

function makeDoc(over: Partial<Document>): Document {
  return {
    id: "d1",
    knowledge_base_id: "kb1",
    organization_id: "o1",
    filename: "a.pdf",
    original_filename: "a.pdf",
    title: "A",
    mime_type: "application/pdf",
    file_size: 2048,
    storage_path: "/x",
    status: "uploaded",
    page_count: null,
    chunk_count: null,
    error_message: null,
    upload_member_id: "u1",
    embedding_id: null,
    metadata: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    ...over,
  };
}

const baseDocs: Document[] = [
  makeDoc({ id: "d1", title: "Alpha", status: "uploaded", file_size: 2048 }),
  makeDoc({ id: "d2", title: "Beta", status: "indexed", chunk_count: 12, file_size: 4096 }),
  makeDoc({ id: "d3", title: "Gamma", status: "failed", error_message: "PDF corrupt", file_size: 8192 }),
];

describe("DocumentList", () => {
  const handlers = {
    onProcess: vi.fn(),
    onViewMetadata: vi.fn(),
    onDelete: vi.fn(),
  };

  it("renders documents with status badges and size", () => {
    render(<DocumentList documents={baseDocs} {...handlers} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Uploaded")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  });

  it("shows a processing spinner for the document being processed", () => {
    render(<DocumentList documents={baseDocs} processingId="d1" {...handlers} />);
    expect(screen.getByText("Processing…")).toBeInTheDocument();
  });

  it("fires action handlers for the matching document", () => {
    render(<DocumentList documents={baseDocs} {...handlers} />);
    fireEvent.click(screen.getByLabelText("Process Alpha"));
    expect(handlers.onProcess).toHaveBeenCalledWith("d1");

    fireEvent.click(screen.getByLabelText("View Alpha"));
    expect(handlers.onViewMetadata).toHaveBeenCalledWith(
      expect.objectContaining({ id: "d1" }),
    );

    fireEvent.click(screen.getByLabelText("Delete Alpha"));
    expect(handlers.onDelete).toHaveBeenCalledWith(
      expect.objectContaining({ id: "d1" }),
    );
  });

  it("renders the failed error inline", () => {
    render(<DocumentList documents={baseDocs} {...handlers} />);
    expect(screen.getByText("PDF corrupt")).toBeInTheDocument();
  });

  it("renders pagination when there are more than a page of documents", () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      makeDoc({ id: `d${i}`, title: `Doc ${i}`, status: "uploaded" }),
    );
    render(<DocumentList documents={many} {...handlers} />);
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
  });

  it("renders an empty state when there are no documents", () => {
    render(<DocumentList documents={[]} {...handlers} />);
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
  });

  it("renders the loading state", () => {
    render(<DocumentList documents={[]} isLoading {...handlers} />);
    expect(screen.getByText("Loading documents...")).toBeInTheDocument();
  });

  it("renders an error state with a retry button", () => {
    const refetch = vi.fn();
    render(
      <DocumentList
        documents={[]}
        isError
        error={new Error("boom")}
        refetch={refetch}
        {...handlers}
      />,
    );
    expect(screen.getByText("Failed to load documents")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
