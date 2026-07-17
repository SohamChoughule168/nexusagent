import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Switch } from "@/features/agent-builder/components/Switch";

describe("Switch", () => {
  it("reflects the checked state via aria-checked", () => {
    render(<Switch checked={false} onCheckedChange={vi.fn()} aria-label="Demo" />);
    const sw = screen.getByRole("switch", { name: "Demo" });
    expect(sw).toHaveAttribute("aria-checked", "false");
  });

  it("fires onCheckedChange with the toggled value", () => {
    const onCheckedChange = vi.fn();
    render(<Switch checked={false} onCheckedChange={onCheckedChange} aria-label="Demo" />);
    fireEvent.click(screen.getByRole("switch", { name: "Demo" }));
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it("does not toggle when disabled", () => {
    const onCheckedChange = vi.fn();
    render(<Switch checked={true} onCheckedChange={onCheckedChange} disabled aria-label="Demo" />);
    fireEvent.click(screen.getByRole("switch", { name: "Demo" }));
    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
