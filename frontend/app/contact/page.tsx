import type { Metadata } from "next";
import {
  Clock,
  Lightbulb,
  Mail,
  MessageSquare,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { ContactForm } from "./contact-form";

export const metadata: Metadata = {
  title: "Contact us",
  description:
    "Get in touch with the NexusAgent team about pricing, enterprise deployments, or a tailored demo.",
  openGraph: {
    title: "Contact NexusAgent",
    description:
      "Talk to our team about pricing, enterprise deployments, or a tailored demo.",
    type: "website",
  },
};

const REASONS = [
  {
    icon: Lightbulb,
    title: "Explore a use case",
    body: "Tell us what you're building and we'll point you to the right agents and grounding strategy.",
  },
  {
    icon: ShieldCheck,
    title: "Enterprise & security",
    body: "SSO, data residency, and self-hosted deployments — talk to us about your requirements.",
  },
  {
    icon: MessageSquare,
    title: "Get a tailored demo",
    body: "We'll ground a workspace in your own docs so you can see NexusAgent on your knowledge.",
  },
];

export default function ContactPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        <section className="border-b border-border bg-muted/30">
          <div className="container py-12">
            <div className="mx-auto max-w-2xl text-center">
              <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                <Sparkles className="h-3.5 w-3.5" /> Contact us
              </span>
              <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
                Let&apos;s talk
              </h1>
              <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
                Whether you&apos;re scoping a pilot or planning an enterprise
                rollout, our team is happy to help. Send a note and we&apos;ll
                get back within one business day.
              </p>
            </div>
          </div>
        </section>

        <section className="container grid gap-8 py-12 lg:grid-cols-[1fr_1.1fr]">
          <aside className="space-y-6">
            <div className="rounded-xl border border-brand-200 bg-brand-50/60 p-6">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-brand-800">
                <Mail className="h-4 w-4 text-brand-600" />
                Why reach out
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                We work closely with every team that evaluates NexusAgent, from
                first question to production launch.
              </p>
            </div>

            <ul className="space-y-4">
              {REASONS.map(({ icon: Icon, title, body }) => (
                <li
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
                </li>
              ))}
            </ul>

            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              Typical response time: within one business day.
            </p>
          </aside>

          <ContactForm />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
