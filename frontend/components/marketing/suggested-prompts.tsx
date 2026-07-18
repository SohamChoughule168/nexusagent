"use client";

import * as React from "react";
import { CornerDownLeft, Sparkles } from "lucide-react";
import { useDemoPromptStore } from "@/store/demo-prompt.store";
import { track } from "@/lib/analytics";

interface PromptGroup {
  label: string;
  prompts: string[];
}

const GROUPS: PromptGroup[] = [
  {
    label: "Get started",
    prompts: [
      "How do I invite my team to a workspace?",
      "What does Brightpath cost?",
      "Can I export my workspace data?",
    ],
  },
  {
    label: "Capabilities",
    prompts: [
      "Do you support single sign-on (SSO)?",
      "How are answers kept grounded in our docs?",
      "Can agents call external tools or APIs?",
    ],
  },
  {
    label: "For my use case",
    prompts: [
      "How would this handle our support tickets?",
      "What does onboarding for a 200-person team look like?",
    ],
  },
];

/**
 * Categorized, clickable suggested prompts for the marketing demo. Clicking a
 * prompt fills the live chat composer (via the demo-prompt store) so the user
 * can send it immediately.
 */
export function SuggestedPrompts() {
  const setPendingPrompt = useDemoPromptStore((s) => s.setPendingPrompt);

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-brand-600" />
        Try asking
      </h2>
      <div className="mt-3 space-y-4">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {group.label}
            </p>
            <ul className="mt-2 space-y-1.5">
              {group.prompts.map((prompt) => (
                <li key={prompt}>
                  <button
                    type="button"
                    onClick={() => {
                      setPendingPrompt(prompt);
                      track("demo_prompt_clicked", { group: group.label });
                    }}
                    className="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <CornerDownLeft className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                    <span>{prompt}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Tip: click a question to drop it into the chat, then press send.
      </p>
    </div>
  );
}

export default SuggestedPrompts;
