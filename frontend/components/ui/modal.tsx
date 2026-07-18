"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  /** Disable closing on backdrop click / Escape. */
  dismissable?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/**
 * Minimal, dependency-free modal: a centered card over a dimmed backdrop.
 * Distinct from `Dialog` (which is Radix-based and richer). Useful for simple
 * confirmations. Rendered through a portal to document.body.
 *
 * Accessibility: traps focus within the dialog, restores focus to the trigger
 * on close, wires `aria-labelledby` / `aria-describedby`, and closes on Escape.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  dismissable = true,
}: ModalProps) {
  const [mounted, setMounted] = React.useState(false);
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  const descId = React.useId();

  React.useEffect(() => {
    setMounted(true);
  }, []);

  // Capture the previously focused element so we can restore it on close.
  const previouslyFocused = React.useRef<HTMLElement | null>(null);
  React.useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;

    // Move focus into the dialog.
    const dialog = dialogRef.current;
    const first = dialog?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? dialog)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && dismissable) {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const focusables = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      );
      if (focusables.length === 0) {
        e.preventDefault();
        dialog.focus();
        return;
      }
      const firstEl = focusables[0];
      const lastEl = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && active === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previouslyFocused.current?.focus?.();
    };
  }, [open, dismissable, onClose]);

  if (!mounted || !open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && dismissable) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          "relative w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg focus:outline-none",
          className,
        )}
      >
        {(title || dismissable) && (
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              {title && (
                <h2
                  id={titleId}
                  className="text-lg font-semibold leading-none tracking-tight"
                >
                  {title}
                </h2>
              )}
              {description && (
                <p id={descId} className="mt-1.5 text-sm text-muted-foreground">
                  {description}
                </p>
              )}
            </div>
            {dismissable && (
              <button
                type="button"
                onClick={onClose}
                className="rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        <div>{children}</div>
        {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export default Modal;
