import { FileText, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types/conversation";

export interface CitationsProps {
  citations: Citation[];
  className?: string;
}

function formatScore(score: number): string {
  const pct = Math.round(Math.min(Math.max(score, 0), 1) * 100);
  return `${pct}%`;
}

/** Compact list of RAG source citations attached to an assistant message. */
export function Citations({ citations, className }: CitationsProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className={cn("mt-3 space-y-2", className)}>
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Quote className="h-3.5 w-3.5" aria-hidden="true" />
        {citations.length} {citations.length === 1 ? "source" : "sources"}
      </p>
      <ul className="space-y-2">
        {citations.map((c, i) => (
          <li
            key={c.chunk_id ?? `${i}`}
            className="rounded-md border border-border bg-muted/30 px-3 py-2"
          >
            <div className="flex items-start gap-2">
              <FileText
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="text-xs leading-relaxed text-foreground/90 line-clamp-3">
                {c.snippet}
              </p>
            </div>
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
              <span className="font-mono">doc:{shortId(c.document_id)}</span>
              <span title={`Relevance: ${c.score}`}>
                {formatScore(c.score)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function shortId(id: string): string {
  if (!id) return "—";
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

export default Citations;
