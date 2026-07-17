import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/features/agent-builder/components/DropdownMenu";

function Harness({ onPick }: { onPick: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button>Open</button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={onPick}>Pick</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem>Other</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

describe("DropdownMenu", () => {
  it("is closed by default and opens on trigger click", () => {
    render(<Harness onPick={vi.fn()} />);
    expect(screen.queryByText("Pick")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Open"));
    expect(screen.getByText("Pick")).toBeInTheDocument();
  });

  it("fires the item onClick and closes the menu", () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);
    fireEvent.click(screen.getByText("Open"));
    fireEvent.click(screen.getByText("Pick"));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Pick")).not.toBeInTheDocument();
  });
});
