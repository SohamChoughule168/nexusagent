import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export interface LoadingStateProps {
  label?: string;
  className?: string;
  /** Render as a full-screen centered overlay (used for route/section loads). */
  fullScreen?: boolean;
}

/** Centered spinner with an optional label. */
export function LoadingState({
  label = "Loading...",
  className,
  fullScreen = false,
}: LoadingStateProps) {
  const content = (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-muted-foreground",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <Spinner size={28} />
      <span className="text-sm">{label}</span>
    </div>
  );

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-background/80 backdrop-blur-sm">
        {content}
      </div>
    );
  }

  return content;
}

export default LoadingState;
