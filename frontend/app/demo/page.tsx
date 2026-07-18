import type { Metadata } from "next";
import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { DemoChat } from "@/components/marketing/demo-chat";
import { SuggestedPrompts } from "@/components/marketing/suggested-prompts";
import { DemoGuidance } from "@/components/marketing/demo-guidance";

export const metadata: Metadata = {
  title: "Live demo",
  description:
    "Talk to Aria, a support agent grounded in a sample help center — a live NexusAgent demo.",
};

export default function DemoPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        <section className="border-b border-border bg-muted/30">
          <div className="container py-12">
            <div className="mx-auto max-w-2xl text-center">
              <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                <Sparkles className="h-3.5 w-3.5" /> Live demo
              </span>
              <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
                Talk to a grounded AI agent
              </h1>
              <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
                This is a real NexusAgent workspace seeded with a sample company.
                The agent retrieves answers from its knowledge base and cites the
                source — no hallucinated replies.
              </p>
            </div>
          </div>
        </section>

        <section className="container grid gap-8 py-12 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            <DemoGuidance />
            <DemoChat />
          </div>

          <aside className="space-y-6">
            <SuggestedPrompts />

            <div className="rounded-xl border border-brand-200 bg-brand-50/60 p-5">
              <h2 className="text-sm font-semibold text-brand-800">
                Want this for your business?
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Ground agents in your own docs, add tools and memory, and deploy
                to your team.
              </p>
              <Button variant="outline" size="sm" className="mt-4" asChild>
                <Link href="/pricing">
                  See plans
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </aside>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
