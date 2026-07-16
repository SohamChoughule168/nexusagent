import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Markdown } from "@/components/chat/markdown";

const writeText = vi.fn();

beforeEach(() => {
  writeText.mockClear();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  // restore
  Object.defineProperty(navigator, "clipboard", {
    value: undefined,
    configurable: true,
  });
});

describe("Markdown (chat renderer)", () => {
  it("renders headings, lists and inline code", () => {
    const { container } = render(
      <Markdown content={"# Title\n\n- one\n- two\n\nUse `code` here"} />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("Title");
    const items = container.querySelectorAll("ul li");
    expect(items.length).toBe(2);
    expect(screen.getByText("code")).toBeInTheDocument();
  });

  it("renders a fenced code block with a copy button", () => {
    const { container } = render(
      <Markdown content={"```js\nconst x = 1;\n```"} />,
    );
    const pre = container.querySelector("pre");
    expect(pre).toBeInTheDocument();
    expect(pre?.textContent).toContain("const x = 1;");
    // language label rendered from the fence
    expect(screen.getByText("js")).toBeInTheDocument();
    // copy button present
    expect(
      screen.getByRole("button", { name: /copy code/i }),
    ).toBeInTheDocument();
  });

  it("copies the code block to the clipboard", async () => {
    render(<Markdown content={"```js\nconst x = 1;\n```"} />);
    const button = screen.getByRole("button", { name: /copy code/i });
    fireEvent.click(button);
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("const x = 1;"));
  });

  it("renders nothing for empty content", () => {
    const { container } = render(<Markdown content={""} />);
    expect(container.firstChild).toBeNull();
  });
});
