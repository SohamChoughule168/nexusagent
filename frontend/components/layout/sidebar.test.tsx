import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import * as nav from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/dashboard"),
}));

describe("Sidebar (layout)", () => {
  it("renders the app brand and primary navigation items", () => {
    render(<Sidebar />);
    expect(screen.getByText("NexusAgent")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Knowledge Base")).toBeInTheDocument();
    expect(screen.getByText("Agent Builder")).toBeInTheDocument();
  });

  it("marks the active route with aria-current", () => {
    vi.mocked(nav.usePathname).mockReturnValue("/dashboard");
    render(<Sidebar />);
    expect(screen.getByText("Dashboard").closest("a")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders the Chat link as an active, navigable route", () => {
    render(<Sidebar />);
    const chatLink = screen.getByText("Chat").closest("a");
    expect(chatLink).toHaveAttribute("href", "/chat");
    expect(screen.getByText("Chat").closest("div")).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});
