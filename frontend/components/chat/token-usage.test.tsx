import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TokenUsage } from "@/components/chat/token-usage";

describe("TokenUsage", () => {
  it("shows tokens and cost derived from the backend", () => {
    render(
      <TokenUsage tokenCount={123} costUsd={0.0042} modelName="anthropic/claude" />,
    );
    expect(screen.getByText("123 tok")).toBeInTheDocument();
    expect(screen.getByText("$0.0042")).toBeInTheDocument();
  });

  it("omits the model name in compact mode", () => {
    render(
      <TokenUsage
        tokenCount={10}
        modelName="anthropic/claude"
        compact
      />,
    );
    expect(screen.getByText("10 tok")).toBeInTheDocument();
    expect(screen.queryByText(/anthropic/)).not.toBeInTheDocument();
  });

  it("renders nothing when no usage data is present", () => {
    const { container } = render(<TokenUsage />);
    expect(container.firstChild).toBeNull();
  });
});
