import * as React from "react";
import { Check, Copy, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CopyButtonProps {
  text: string;
  label?: string;
  className?: string;
  "aria-label"?: string;
}

/** Reusable clipboard copy button with a brief "copied" confirmation. */
export function CopyButton({
  text,
  label = "Copy",
  className,
  "aria-label": ariaLabel,
}: CopyButtonProps) {
  const [copied, setCopied] = React.useState(false);

  const onCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable; ignore.
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={ariaLabel ?? label}
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
      {copied ? "Copied" : label}
    </button>
  );
}

export interface MessageActionsProps {
  content: string;
  onRetry?: () => void;
  canRetry?: boolean;
  className?: string;
}

/** Copy + (optional) retry controls shown on a message. */
export function MessageActions({
  content,
  onRetry,
  canRetry,
  className,
}: MessageActionsProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-1",
        className,
      )}
    >
      <CopyButton text={content} label="Copy" />
      {canRetry && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Retry message"
        >
          <RotateCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}

export default MessageActions;
