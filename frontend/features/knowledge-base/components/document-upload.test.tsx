import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DocumentUpload } from "@/features/knowledge-base/components/document-upload";

vi.mock("@/hooks/use-documents", () => ({
  useDocuments: vi.fn(() => ({
    uploadDocumentAsync: vi.fn().mockResolvedValue({ id: "d1", status: "uploaded" }),
  })),
}));

import * as docs from "@/hooks/use-documents";

const pdf = () => new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" });

describe("DocumentUpload", () => {
  let uploadDocumentAsync: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    uploadDocumentAsync = vi.fn().mockResolvedValue({ id: "d1", status: "uploaded" });
    vi.mocked(docs.useDocuments).mockReturnValue({
      uploadDocumentAsync,
    } as never);
  });

  it("renders the dropzone", () => {
    render(<DocumentUpload knowledgeBaseId="kb1" />);
    expect(
      screen.getByText(/Drag & drop PDFs here/i),
    ).toBeInTheDocument();
  });

  it("uploads a PDF selected via the file input", async () => {
    const { container } = render(<DocumentUpload knowledgeBaseId="kb1" />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pdf()] } });

    await waitFor(() => expect(uploadDocumentAsync).toHaveBeenCalled());
    const call = (uploadDocumentAsync as any).mock.calls[0][0];
    expect(call.file.name).toBe("report.pdf");
    await waitFor(() => expect(screen.getByText("Uploaded")).toBeInTheDocument());
  });

  it("rejects non-PDF files without calling the uploader", async () => {
    render(<DocumentUpload knowledgeBaseId="kb1" />);
    const input = screen.getByLabelText(/Upload documents/i, {
      selector: "[role=button]",
    }) as HTMLElement;
    // Non-PDF via drop is rejected client-side.
    const txt = new File(["hi"], "notes.txt", { type: "text/plain" });
    fireEvent.drop(input, { dataTransfer: { files: [txt] } });

    await waitFor(() =>
      expect(screen.getByText(/Only PDF files are supported/i)).toBeInTheDocument(),
    );
    expect(uploadDocumentAsync).not.toHaveBeenCalled();
  });

  it("uploads a file dropped onto the dropzone", async () => {
    render(<DocumentUpload knowledgeBaseId="kb1" />);
    const dropzone = screen.getByLabelText(/Upload documents/i, {
      selector: "[role=button]",
    }) as HTMLElement;
    fireEvent.drop(dropzone, { dataTransfer: { files: [pdf()] } });

    await waitFor(() => expect(uploadDocumentAsync).toHaveBeenCalled());
  });

  it("shows a progress bar while uploading", async () => {
    uploadDocumentAsync = vi
      .fn()
      .mockImplementation(
        async ({ onProgress }: { onProgress: (p: number) => void }) => {
          onProgress(50);
          // Never settle — keeps the uploading state observable for the test.
          return new Promise(() => {});
        },
      );
    vi.mocked(docs.useDocuments).mockReturnValue({
      uploadDocumentAsync,
    } as never);

    const { container } = render(<DocumentUpload knowledgeBaseId="kb1" />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pdf()] } });

    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "50");
  });
});
