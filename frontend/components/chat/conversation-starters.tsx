"use client";

import * as React from "react";
import { useDemoPromptStore } from "@/store/demo-prompt.store";

export interface ConversationStartersProps {
  starters: string[];
}

/**
 * Clickable starter chips shown above the composer when a conversation is
 * empty. Clicking drops the text into the composer (demo store) so the user
 * can send it. Scoped to the demo via the `starters` prop.
 */
export function ConversationStarters({ starters }: ConversationStartersProps) {
  const setPendingPrompt = useDemoPromptStore((s) => s.setPendingPrompt);

  if (starters.length === 0) return null;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-3">
      <p className="mb-2 text-center text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Or start with one of these
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {starters.map((starter) => (
          <button
            key={starter}
            type="button"
            onClick={() => setPendingPrompt(starter)}
            className="rounded-full border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-brand-300 hover:bg-brand-50/60 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {starter}
          </button>
        ))}
      </div>
    </div>
  );
}

export default ConversationStarters;
