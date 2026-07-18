"use client";

import * as React from "react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/chat/markdown";
import { LogoMark } from "@/components/marketing/logo";
import type { ShowcaseMessage } from "@/lib/demo-content";

/**
 * Static, animated showcase of a grounded RAG conversation. The final
 * assistant message "types" itself out on mount to mimic the live product;
 * earlier messages render immediately. Uses the same Markdown renderer as the
 * chat UI so the look matches the real thing.
 */
export function ShowcaseChat({
  messages,
  className,
}: {
  messages: ShowcaseMessage[];
  className?: string;
}) {
  const lastAssistantIdx = messages.reduce(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1,
  );
  const last = lastAssistantIdx >= 0 ? messages[lastAssistantIdx] : null;
  const lastText = last?.content ?? "";

  const [typed, setTyped] = React.useState(lastText);
  const [done, setDone] = React.useState(false);

  React.useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !lastText) {
      setDone(true);
      return;
    }
    setTyped("");
    setDone(false);
    let i = 0;
    const step = 2;
    const id = window.setInterval(() => {
      i = Math.min(lastText.length, i + step);
      setTyped(lastText.slice(0, i));
      if (i >= lastText.length) {
        window.clearInterval(id);
        setDone(true);
      }
    }, 14);
    return () => window.clearInterval(id);
  }, [lastText]);

  return (
    <div
      className={cn(
        "flex flex-col gap-4 rounded-2xl border border-border bg-card p-4 shadow-xl shadow-brand-500/5 sm:p-5",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-border pb-3 text-sm font-medium text-muted-foreground">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-500/10 text-brand-600">
          <Sparkles className="h-3.5 w-3.5" />
        </span>
        Live with Aria · Brightpath Support
      </div>

      {messages.map((m, idx) => {
        if (m.role === "user") {
          return (
            <div key={idx} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm sm:max-w-[75%]">
                <p className="whitespace-pre-wrap break-words">{m.content}</p>
              </div>
            </div>
          );
        }

        const isLast = idx === lastAssistantIdx;
        const shown = isLast ? typed : m.content;
        const showCitations = isLast && done && m.citations?.length;

        return (
          <div key={idx} className="flex justify-start gap-2.5">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-500/10">
              <LogoMark className="h-4 w-4" />
            </span>
            <div className="max-w-[85%] sm:max-w-[78%]">
              <div className="rounded-2xl rounded-tl-sm border border-border bg-muted/50 px-4 py-2.5 text-sm leading-relaxed">
                {isLast && !done ? (
                  <p className="whitespace-pre-wrap break-words">
                    {shown}
                    <span className="brand-pulse ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 bg-brand-500" />
                  </p>
                ) : (
                  <Markdown content={shown} />
                )}
              </div>
              {showCitations && (
                <div className="mt-2 space-y-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {m.citations!.map((c) => (
                      <span
                        key={c.label}
                        className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground"
                        title={c.source}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                        {c.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default ShowcaseChat;
