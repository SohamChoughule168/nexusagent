import { cn } from "@/lib/utils";

export interface TypingIndicatorProps {
  className?: string;
}

/** Three-dot "assistant is typing" animation, used before the first token arrives. */
export function TypingIndicator({ className }: TypingIndicatorProps) {
  return (
    <div
      className={cn("flex items-center gap-1 py-1", className)}
      role="status"
      aria-label="Assistant is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/60"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  );
}

export default TypingIndicator;
