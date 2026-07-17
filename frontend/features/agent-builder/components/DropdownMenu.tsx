"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Minimal, dependency-free dropdown menu. Mirrors the small slice of the
 * Radix dropdown API used by AgentCard (Trigger/Content/Item/Separator) so the
 * feature doesn't pull in an extra Radix package. Closes on outside click or
 * Escape.
 */

interface DropdownContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DropdownContext = React.createContext<DropdownContextValue | null>(null);

export function DropdownMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <DropdownContext.Provider value={{ open, setOpen }}>
      <div ref={ref} className="relative inline-block">
        {children}
      </div>
    </DropdownContext.Provider>
  );
}

export function DropdownMenuTrigger({
  asChild,
  children,
}: {
  asChild?: boolean;
  children: React.ReactNode;
}) {
  const ctx = React.useContext(DropdownContext);
  if (!ctx) return null;

  const toggle = () => ctx.setOpen(!ctx.open);

  if (asChild && React.isValidElement(children)) {
    const child = children as React.ReactElement<Record<string, unknown>>;
    const childOnClick = child.props.onClick as
      | ((e: React.MouseEvent) => void)
      | undefined;
    return React.cloneElement(child, {
      onClick: (e: React.MouseEvent) => {
        childOnClick?.(e);
        toggle();
      },
      "aria-haspopup": "menu",
      "aria-expanded": ctx.open,
    });
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-haspopup="menu"
      aria-expanded={ctx.open}
    >
      {children}
    </button>
  );
}

export function DropdownMenuContent({
  align = "end",
  children,
}: {
  align?: "start" | "end";
  children: React.ReactNode;
}) {
  const ctx = React.useContext(DropdownContext);
  if (!ctx || !ctx.open) return null;

  return (
    <div
      role="menu"
      className={cn(
        "absolute z-50 mt-1 min-w-[10rem] rounded-md border bg-popover p-1 text-popover-foreground shadow-md",
        align === "end" ? "right-0" : "left-0",
      )}
    >
      {children}
    </div>
  );
}

export function DropdownMenuItem({
  onClick,
  className,
  children,
}: {
  onClick?: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  const ctx = React.useContext(DropdownContext);
  return (
    <button
      type="button"
      role="menuitem"
      onClick={() => {
        onClick?.();
        ctx?.setOpen(false);
      }}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none transition-colors hover:bg-accent focus:bg-accent",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function DropdownMenuSeparator() {
  return <div className="my-1 h-px bg-muted" />;
}
