import Link from "next/link";
import { Check, Minus } from "lucide-react";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { PricingFaq, type FaqItem } from "@/components/marketing/pricing-faq";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "NexusAgent plans for every team — from a free starter workspace to enterprise with SSO, RBAC, and dedicated support.",
};

interface Plan {
  name: string;
  price: string;
  period: string;
  blurb: string;
  cta: string;
  href: string;
  featured?: boolean;
  highlights: string[];
}

const PLANS: Plan[] = [
  {
    name: "Starter",
    price: "$0",
    period: "forever",
    blurb: "For trying NexusAgent and small personal projects.",
    cta: "Start free demo",
    href: "/demo",
    highlights: [
      "1 agent",
      "1 knowledge base · up to 50 documents",
      "1,000 messages / month",
      "Shared models",
      "Community support",
    ],
  },
  {
    name: "Growth",
    price: "$99",
    period: "/ month",
    blurb: "For teams putting agents in front of customers.",
    cta: "Start free trial",
    href: "/demo",
    featured: true,
    highlights: [
      "5 agents",
      "10 knowledge bases · up to 2,000 documents",
      "25,000 messages / month",
      "Multi-agent routing & orchestration",
      "Tools & function calling",
      "API access · email support",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "talk to us",
    blurb: "For organizations with security and scale needs.",
    cta: "Book a demo",
    href: "/demo",
    highlights: [
      "Unlimited agents & knowledge bases",
      "SSO / SAML & advanced RBAC",
      "Dedicated or bring-your-own models",
      "VPC / self-hosted option",
      "Audit logs & priority support + SLA",
    ],
  },
];

const COMPARISON: { feature: string; values: [string, string, string] }[] = [
  { feature: "Agents", values: ["1", "5", "Unlimited"] },
  { feature: "Knowledge bases", values: ["1", "10", "Unlimited"] },
  { feature: "Documents per KB", values: ["50", "2,000", "Custom"] },
  { feature: "Messages / month", values: ["1,000", "25,000", "Custom"] },
  { feature: "RAG & citations", values: ["Yes", "Yes", "Yes"] },
  { feature: "Conversation memory", values: ["Yes", "Yes", "Yes"] },
  { feature: "Multi-agent routing", values: ["—", "Yes", "Yes"] },
  { feature: "Tools & function calling", values: ["—", "Yes", "Yes"] },
  { feature: "API access", values: ["—", "Yes", "Yes"] },
  { feature: "SSO / SAML", values: ["—", "—", "Yes"] },
  { feature: "VPC / self-hosted", values: ["—", "—", "Yes"] },
  { feature: "Support", values: ["Community", "Email", "Priority + SLA"] },
];

const FAQ: FaqItem[] = [
  {
    q: "Can I try NexusAgent before paying?",
    a: "Yes. The Starter plan is free forever, and you can talk to a fully grounded demo agent in the live demo without creating an account.",
  },
  {
    q: "How is my data isolated from other customers?",
    a: "Every record is scoped to your organization and enforced with PostgreSQL row-level security plus an application-layer tenant check. Your knowledge, conversations, and memory never mix with another tenant's.",
  },
  {
    q: "Which AI models can I use?",
    a: "Growth and Enterprise plans can bring their own provider keys (OpenRouter, OpenAI, Anthropic, and more) or use shared models. Starter uses shared models.",
  },
  {
    q: "Can agents call external tools and APIs?",
    a: "Yes. Agents on Growth and above can use a tenant-scoped tool registry with schema validation, function calling, and built-in tools like webhooks, lead capture, and human hand-off.",
  },
  {
    q: "Do you support SSO and advanced permissions?",
    a: "SSO / SAML and advanced RBAC are included on Enterprise, along with audit logs and a priority support SLA.",
  },
  {
    q: "Is there a self-hosted option?",
    a: "Enterprise customers can run NexusAgent in their own VPC or on-premises. Talk to us about deployment and compliance requirements.",
  },
];

function Cell({ value }: { value: string }) {
  if (value === "Yes")
    return <Check className="mx-auto h-4 w-4 text-brand-600" />;
  if (value === "—" || value === "")
    return <Minus className="mx-auto h-4 w-4 text-muted-foreground/50" />;
  return <span className="text-sm text-foreground">{value}</span>;
}

export default function PricingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex-1">
        {/* Header */}
        <section className="relative overflow-hidden border-b border-border">
          <div className="absolute inset-0 -z-10 bg-grid opacity-40" />
          <div className="container py-16 text-center">
            <Badge
              variant="secondary"
              className="mb-4 border-brand-200 bg-brand-50 text-brand-700"
            >
              Pricing
            </Badge>
            <h1 className="mx-auto max-w-2xl text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
              Plans that scale from first agent to enterprise
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              Start free, prove value with a grounded agent, then grow into team
              and enterprise tiers. No surprise overage bills.
            </p>
          </div>
        </section>

        {/* Plan cards */}
        <section className="container -mt-8 pb-8">
          <div className="grid gap-6 lg:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={cn(
                  "relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm",
                  plan.featured
                    ? "border-brand-400 shadow-lg shadow-brand-500/10 ring-1 ring-brand-400"
                    : "border-border",
                )}
              >
                {plan.featured && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 px-3 py-1 text-xs font-semibold text-white">
                    Most popular
                  </span>
                )}
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan.blurb}
                </p>
                <div className="mt-5 flex items-baseline gap-1">
                  <span className="text-4xl font-extrabold tracking-tight">
                    {plan.price}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {plan.period}
                  </span>
                </div>
                <Button
                  className="mt-5"
                  variant={plan.featured ? "default" : "outline"}
                  asChild
                >
                  <Link href={plan.href}>{plan.cta}</Link>
                </Button>
                <ul className="mt-6 space-y-3">
                  {plan.highlights.map((h) => (
                    <li key={h} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                      <span className="text-muted-foreground">{h}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* Comparison table */}
        <section className="container py-12">
          <h2 className="text-center text-2xl font-bold tracking-tight sm:text-3xl">
            Compare plans
          </h2>
          <div className="mt-8 overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="bg-muted/40">
                  <th className="px-5 py-3 text-left font-semibold">Feature</th>
                  {PLANS.map((p) => (
                    <th
                      key={p.name}
                      className={cn(
                        "px-5 py-3 text-center font-semibold",
                        p.featured && "text-brand-700",
                      )}
                    >
                      {p.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row, i) => (
                  <tr
                    key={row.feature}
                    className={i % 2 ? "bg-muted/20" : "bg-card"}
                  >
                    <td className="px-5 py-3 text-left font-medium text-foreground">
                      {row.feature}
                    </td>
                    {row.values.map((v, j) => (
                      <td key={j} className="px-5 py-3 text-center">
                        <Cell value={v} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* FAQ */}
        <section className="container max-w-3xl py-12">
          <h2 className="text-center text-2xl font-bold tracking-tight sm:text-3xl">
            Frequently asked questions
          </h2>
          <div className="mt-8">
            <PricingFaq items={FAQ} />
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-border bg-muted/30">
          <div className="container py-16 text-center">
            <h2 className="mx-auto max-w-xl text-3xl font-bold tracking-tight">
              Not sure which plan fits?
            </h2>
            <p className="mx-auto mt-3 max-w-lg text-muted-foreground">
              Start with the free demo and talk to us about volume, security,
              and deployment.
            </p>
            <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
              <Button size="lg" asChild>
                <Link href="/demo">Launch live demo</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/">Back to home</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
