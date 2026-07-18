import { cn } from "@/lib/utils";

/**
 * Shimmer placeholder block. Use to reserve layout space while content loads
 * so the page doesn't jump (no CLS). Pair with `animate-pulse`.
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export default Skeleton;
