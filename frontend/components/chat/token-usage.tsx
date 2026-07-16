import { Coins } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TokenUsageProps {
  tokenCount?: number | null;
  costUsd?: number | null;
  modelName?: string | null;
  modelProvider?: string | null;
  /** Compact form for the message footer. */
  compact?: boolean;
  className?: string;
}

function formatCost(cost: number): string {
  if (cost <= 0) return "$0.00";
  return `$${cost.toFixed(4)}`;
}

/**
 * Token usage display. The backend persists `token_count` / `cost_usd` /
 * `model_name` per message and totals on the conversation, so we only render
 * when present.
 */
export function TokenUsage({
  tokenCount,
  costUsd,
  modelName,
  modelProvider,
  compact = false,
  className,
}: TokenUsageProps) {
  const hasTokens = typeof tokenCount === "number" && tokenCount > 0;
  const hasCost = typeof costUsd === "number" && costUsd > 0;
  const hasModel = Boolean(modelName || modelProvider);
  if (!hasTokens && !hasCost && !hasModel) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs text-muted-foreground",
        className,
      )}
      title={
        hasModel
          ? `Model: ${modelName ?? modelProvider}`
          : undefined
      }
    >
      <Coins className="h-3.5 w-3.5" aria-hidden="true" />
      {hasTokens && <span>{tokenCount} tok</span>}
      {hasTokens && hasCost && <span aria-hidden="true">·</span>}
      {hasCost && <span>{formatCost(costUsd as number)}</span>}
      {!compact && hasModel && (
        <span className="text-muted-foreground/70">· {modelName ?? modelProvider}</span>
      )}
    </span>
  );
}

export default TokenUsage;
