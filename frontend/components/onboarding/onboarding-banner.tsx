"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Rocket, X } from "lucide-react";

const STORAGE_KEY = "nexus_onboarding_seen";

const STEPS = [
  {
    href: "/agents",
    label: "Create your first agent",
    body: "Compose an agent grounded in your knowledge.",
  },
  {
    href: "/demo",
    label: "Try the live demo",
    body: "See a grounded agent answer with citations.",
  },
  {
    href: "/#docs",
    label: "Read the docs",
    body: "Learn about tools, memory, and routing.",
  },
];

/**
 * First-run guidance banner. Shown once for new users (dismissal persisted in
 * localStorage), it points at the three highest-value next steps. Purely
 * client-side — no backend state.
 */
export function OnboardingBanner() {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
    } catch {
      // localStorage unavailable (e.g. private mode) — show guidance anyway.
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
    <section
      aria-label="Getting started"
      className="relative overflow-hidden rounded-xl border border-brand-200 bg-gradient-to-br from-brand-50/80 to-card p-5 sm:p-6"
    >
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss getting started guide"
        className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600">
          <Rocket className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-brand-900">
            Welcome to NexusAgent
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Three quick steps to get the most out of your workspace.
          </p>
        </div>
      </div>

      <ol className="mt-4 grid gap-2 sm:grid-cols-3">
        {STEPS.map((step, i) => (
          <li key={step.href}>
            <Link
              href={step.href}
              onClick={dismiss}
              className="group flex h-full flex-col rounded-lg border border-border bg-background/70 p-3 transition-colors hover:border-brand-300 hover:bg-background"
            >
              <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <CheckCircle2 className="h-3.5 w-3.5 text-brand-500" />
                Step {i + 1}
              </span>
              <span className="mt-1 text-sm font-semibold">{step.label}</span>
              <span className="mt-0.5 text-xs text-muted-foreground">
                {step.body}
              </span>
              <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-700 opacity-0 transition-opacity group-hover:opacity-100">
                Go <ArrowRight className="h-3 w-3" />
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default OnboardingBanner;
