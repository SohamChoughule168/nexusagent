import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentStatusBadge } from "@/features/knowledge-base/components/document-status-badge";
import { documentStatusLabel, documentStatusVariant } from "@/types/knowledge-base";

describe("DocumentStatusBadge", () => {
  it.each([
    ["uploaded", "Uploaded"],
    ["processed", "Processed"],
    ["indexed", "Indexed"],
    ["failed", "Failed"],
  ] as const)("renders the %s status", (status, label) => {
    render(<DocumentStatusBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toBeInTheDocument();
    // Badge variant is encoded in a data attribute via the shared helper.
    expect(documentStatusVariant(status)).toBeTruthy();
  });

  it("maps each status to a known human label", () => {
    expect(documentStatusLabel("uploaded")).toBe("Uploaded");
    expect(documentStatusLabel("indexed")).toBe("Indexed");
    expect(documentStatusLabel("failed")).toBe("Failed");
  });

  it("uses the destructive variant for failed documents", () => {
    expect(documentStatusVariant("failed")).toBe("destructive");
    expect(documentStatusVariant("indexed")).toBe("success");
  });
});
