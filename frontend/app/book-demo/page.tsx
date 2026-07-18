import type { Metadata } from "next";
import { CalendarClock, Presentation, Sparkles, Users } from "lucide-react";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { BookDemoForm } from "./book-demo-form";

export const metadata: Metadata = {
  title: "Book a demo",
  description:
    "Request a personalized NexusAgent demo grounded in your own knowledge — see agents, tools, and memory on your use case.",
  openGraph: {
    title: "Book a NexusAgent demo",
    description:
      "Get a personalized demo grounded in your own knowledge and use case.",
    type: "website",
  },
};

const HIGHLIGHTS = [
  {
    icon: Presentation,
    title: "Tailored to you",
    body: "We ground the demo in your docs and walk through your exact workflow.",
  },
  {
    icon: Users,
    title: "Bring your team",
    body: "Invite stakeholders — the session is shaped around your questions.",
  },
  {
    icon: CalendarClock,
    title: "On your schedule",
    body: "Pick a time that works. Most demos run 30–45 minutes.",
  },
];

export default function BookDemoPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        <section className="border-b border-border bg-muted/30">
          <div className="container py-12">
            <div className="mx-auto max-w-2xl text-center">
              <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                <Sparkles className="h-3.5 w-3.5" /> Book a demo
              </span>
              <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
                See NexusAgent on your terms
              </h1>
              <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
                Tell us a little about your team and what you&apos;re building.
                We&apos;ll set up a live, grounded demo and walk through it with
                you.
              </p>
            </div>
          </div>
        </section>

        <section className="container grid gap-8 py-12 lg:grid-cols-[1fr_1.1fr]">
          <aside className="space-y-4">
            {HIGHLIGHTS.map(({ icon: Icon, title, body }) => (
              <div
                key={title}
                className="flex gap-3 rounded-xl border border-border bg-card p-4"
              >
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600">
                  <Icon className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">{title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{body}</p>
                </div>
              </div>
            ))}
          </aside>

          <BookDemoForm />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
