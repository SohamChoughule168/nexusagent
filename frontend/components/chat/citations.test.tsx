import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Citations } from "@/components/chat/citations";
import type { Citation } from "@/types/conversation";

const sources: Citation[] = [
  {
    chunk_id: "c1",
    document_id: "d1111111-1111-1111-1111-111111111111",
    score: 0.92,
    snippet: "The quick brown fox",
  },
];

describe("Citations", () => {
  it("renders the source list with snippet and relevance", () => {
    render(<Citations citations={sources} />);
    expect(screen.getByText("1 source")).toBeInTheDocument();
    expect(screen.getByText("The quick brown fox")).toBeInTheDocument();
    // score formated as a percentage
    expect(screen.getByText("92%")).toBeInTheDocument();
    // short document id shown
    expect(screen.getByText(/doc:d1111111…/)).toBeInTheDocument();
  });

  it("uses plural label for multiple sources", () => {
    render(
      <Citations
        citations={[
          { ...sources[0], chunk_id: "a" },
          { ...sources[0], chunk_id: "b" },
        ]}
      />,
    );
    expect(screen.getByText("2 sources")).toBeInTheDocument();
  });

  it("renders nothing without citations", () => {
    const { container } = render(<Citations citations={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
