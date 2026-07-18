"use client";

import * as React from "react";
import { Info, X } from "lucide-react";

const STORAGE_KEY = "nexus_demo_guide_seen";

/**
 * First-time guidance for the demo page. Shown once (dismissal persisted in
 * localStorage) to orient new visitors. Purely client-side.
 */
export function DemoGuidance() {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  const dismiss = React.useCallback(() => {
    setVisible(false);
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // ignore persistence failure
    }
  }, []);

  if (!visible) return null;

  return (
    <div
      role="region"
      aria-label="Demo tips"
      className="flex items-start gap-3 rounded-xl border border-brand-200 bg-brand-50/60 p-4"
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
      <div className="flex-1 text-sm text-muted-foreground">
        <span className="font-medium text-brand-900">New here?</span> Launch the
        demo, then click any <span className="font-medium">“Try asking”</span>{" "}
        question to drop it into the chat. Aria cites its sources, so you can see
        exactly where each answer comes from.
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss tips"
        className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export default DemoGuidance;
