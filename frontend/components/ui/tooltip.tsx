"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface TooltipProps {
  /** Tooltip text/contents. */
  content: React.ReactNode;
  /** Where to place the bubble relative to the trigger. */
  side?: "top" | "bottom" | "right" | "left";
  /** Render-prop child — must accept a ref and the wiring props. */
  children: React.ReactElement;
  className?: string;
}

const SIDE_CLASSES: Record<NonNullable<TooltipProps["side"]>, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
};

/**
 * Lightweight, accessible tooltip. Shows on hover and keyboard focus, hides on
 * blur, mouse-leave, or Escape. Wires `aria-describedby` from the trigger to
 * the tooltip so screen readers announce it.
 */
export function Tooltip({
  content,
  side = "top",
  children,
  className,
}: TooltipProps) {
  const [open, setOpen] = React.useState(false);
  const id = React.useId();

  const child = React.Children.only(children);
  const childProps = child.props as {
    onKeyDown?: (e: React.KeyboardEvent) => void;
  };
  const trigger = React.cloneElement(child, {
    "aria-describedby": open ? id : undefined,
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
    onFocus: () => setOpen(true),
    onBlur: () => setOpen(false),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      childProps.onKeyDown?.(e);
    },
  } as Partial<React.HTMLAttributes<HTMLElement>>);

  return (
    <span className="relative inline-flex">
      {trigger}
      {open && (
        <span
          role="tooltip"
          id={id}
          className={cn(
            "pointer-events-none absolute z-50 w-max max-w-xs rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs font-medium text-popover-foreground shadow-md",
            "animate-in fade-in-0 zoom-in-95",
            SIDE_CLASSES[side],
            className,
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}

export default Tooltip;
