import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SpinnerProps {
  className?: string;
  /** Diameter in pixels (sets width & height). */
  size?: number;
  "aria-label"?: string;
}

/** Accessible loading spinner (announced to screen readers). */
export function Spinner({
  className,
  size = 24,
  "aria-label": ariaLabel = "Loading",
}: SpinnerProps) {
  return (
    <Loader2
      className={cn("animate-spin text-muted-foreground", className)}
      width={size}
      height={size}
      role="status"
      aria-label={ariaLabel}
    />
  );
}

export default Spinner;
