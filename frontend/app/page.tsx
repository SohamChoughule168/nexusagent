import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Brain,
  ShieldCheck,
  Sparkles,
  Workflow,
  Wrench,
  Activity,
  Headphones,
  GraduationCap,
  TrendingUp,
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { FeatureCard } from "@/components/marketing/feature-card";
import { ShowcaseChat } from "@/components/marketing/showcase-chat";
import { SHOWCASE_CONVERSATION, TRUST_STATS } from "@/lib/demo-content";

const FEATURES = [
  {
    icon: <BookOpen className="h-5 w-5" />,
    title: "Answers from your knowledge",
    description:
      "Ground agents in your PDFs, docs, and help center with retrieval-augmented generation. Replies cite the source, so customers get facts, not hallucinations.",
  },
  {
    icon: <Workflow className="h-5 w-5" />,
    title: "Multi-agent orchestration",
    description:
      "Route each request to the best agent and let agents plan, delegate, and recover from failures — one conversation, many specialized agents working together.",
  },
  {
    icon: <Brain className="h-5 w-5" />,
    title: "Conversation memory",
    description:
      "Short-term context plus long-term, semantic memory that consolidates and ranks what matters, so agents remember customers across sessions.",
  },
  {
    icon: <Wrench className="h-5 w-5" />,
    title: "Tools & function calling",
    description:
      "Give agents real capabilities — lookups, webhooks, lead capture, human hand-off — through a tenant-scoped tool registry with schema validation.",
  },
  {
    icon: <ShieldCheck className="h-5 w-5" />,
    title: "Multi-tenant & secure by default",
    description:
      "Every record is scoped to your organization with PostgreSQL row-level security, JWT auth, Argon2 hashing, and RBAC (Owner / Admin / Member / Viewer).",
  },
  {
    icon: <Activity className="h-5 w-5" />,
    title: "Observable in production",
    description:
      "Prometheus metrics, structured logs, and dashboards for every agent, conversation, and token — so you can see exactly what your agents are doing.",
  },
];

const STEPS = [
  {
    title: "Connect your knowledge",
    description:
      "Upload PDFs and documents or point agents at your help center. NexusAgent chunks, embeds, and indexes them automatically.",
    icon: <BookOpen className="h-5 w-5" />,
  },
  {
    title: "Build your agent",
    description:
      "Set the system prompt, pick the model, attach knowledge bases, tools, and memory. Clone a starter agent in minutes.",
    icon: <Bot className="h-5 w-5" />,
  },
  {
    title: "Deploy & chat",
    description:
      "Ship the agent to your team or customers. Watch conversations, memory, and tool calls live from the dashboard.",
    icon: <Sparkles className="h-5 w-5" />,
  },
];

const USE_CASES = [
  {
    icon: <Headphones className="h-5 w-5" />,
    title: "Customer support",
    description:
      "Deflect tickets with an agent that answers from your help center and escalates to a human with full context when it's stuck.",
  },
  {
    icon: <GraduationCap className="h-5 w-5" />,
    title: "Employee help desk",
    description:
      "Give every employee a grounded assistant for HR, IT, and internal policy — private to your organization.",
  },
  {
    icon: <TrendingUp className="h-5 w-5" />,
    title: "Sales enablement",
    description:
      "Put product specs, pricing, and battlecards in an agent your reps can query mid-call, in plain language.",
  },
  {
    icon: <Bot className="h-5 w-5" />,
    title: "Onboarding concierge",
    description:
      "Welcome new users with a guided agent that knows your docs and remembers where each person left off.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 -z-10 bg-grid opacity-[0.4]" />
          <div className="absolute left-1/2 top-0 -z-10 h-[420px] w-[820px] -translate-x-1/2 rounded-full bg-brand-500/15 blur-3xl" />
          <div className="container grid items-center gap-12 py-16 lg:grid-cols-2 lg:py-24">
            <div>
              <Badge
                variant="secondary"
                className="mb-5 gap-1.5 border-brand-200 bg-brand-50 text-brand-700"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Multi-agent routing is here
              </Badge>
              <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl">
                The AI agent platform that{" "}
                <span className="text-gradient">knows your business</span>
              </h1>
              <p className="mt-5 max-w-xl text-pretty text-lg text-muted-foreground">
                Build, ground, and orchestrate autonomous AI agents on your own
                knowledge. NexusAgent adds memory, tools, and multi-agent
                routing — so your agents answer with your facts, not guesses.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button size="lg" asChild>
                  <Link href="/demo">
                    Start free demo
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button size="lg" variant="outline" asChild>
                  <Link href="/pricing">View pricing</Link>
                </Button>
              </div>
              <p className="mt-4 text-sm text-muted-foreground">
                No credit card · Your data stays in your tenant
              </p>
            </div>

            <div className="relative">
              <ShowcaseChat messages={SHOWCASE_CONVERSATION} />
            </div>
          </div>
        </section>

        {/* Trust stats */}
        <section className="border-y border-border bg-muted/30">
          <div className="container grid grid-cols-2 gap-6 py-8 md:grid-cols-4">
            {TRUST_STATS.map((s) => (
              <div key={s.label} className="text-center">
                <div className="text-xl font-bold text-foreground sm:text-2xl">
                  {s.value}
                </div>
                <div className="mt-1 text-xs text-muted-foreground sm:text-sm">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Features */}
        <section id="features" className="container scroll-mt-20 py-20">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Everything you need to ship real agents
            </h2>
            <p className="mt-4 text-muted-foreground">
              A complete platform — retrieval, memory, orchestration, tools, and
              the security enterprises expect — in one multi-tenant service.
            </p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <FeatureCard
                key={f.title}
                icon={f.icon}
                title={f.title}
                description={f.description}
              />
            ))}
          </div>
        </section>

        {/* How it works */}
        <section
          id="how-it-works"
          className="scroll-mt-20 border-y border-border bg-muted/30 py-20"
        >
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                From docs to deployed in an afternoon
              </h2>
              <p className="mt-4 text-muted-foreground">
                No custom infrastructure. Connect knowledge, build an agent,
                and start chatting.
              </p>
            </div>
            <div className="mt-12 grid gap-8 md:grid-cols-3">
              {STEPS.map((step, i) => (
                <div key={step.title} className="relative">
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500 text-white">
                    {step.icon}
                  </div>
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-sm font-semibold text-brand-600">
                      Step {i + 1}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold">{step.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                    {step.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Use cases */}
        <section id="use-cases" className="container scroll-mt-20 py-20">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Built for the conversations that matter
            </h2>
            <p className="mt-4 text-muted-foreground">
              One platform, many teams. Ground a different agent in a different
              knowledge base for each job.
            </p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {USE_CASES.map((u) => (
              <div
                key={u.title}
                className="rounded-xl border border-border bg-card p-6"
              >
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600">
                  {u.icon}
                </div>
                <h3 className="mb-1.5 text-base font-semibold">{u.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {u.description}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Resources / Docs */}
        <section
          id="docs"
          className="scroll-mt-20 border-y border-border bg-muted/30 py-20"
        >
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                Resources to get you going
              </h2>
              <p className="mt-4 text-muted-foreground">
                Start with the live demo, then follow the guides in the
                repository to stand up your own workspace.
              </p>
            </div>
            <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { title: "Run the live demo", body: "Talk to a grounded agent in seconds.", href: "/demo", cta: "Open demo" },
                { title: "Quickstart", body: "Spin up the local stack and seed the demo workspace.", href: "/demo", cta: "See how" },
                { title: "Build an agent", body: "Prompts, knowledge, tools, and memory.", href: "/demo", cta: "Learn" },
                { title: "Knowledge bases", body: "Ingest PDFs and enable RAG retrieval.", href: "/demo", cta: "Learn" },
              ].map((r) => (
                <Link
                  key={r.title}
                  href={r.href}
                  className="group rounded-xl border border-border bg-card p-6 transition-colors hover:border-brand-300"
                >
                  <h3 className="text-base font-semibold">{r.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    {r.body}
                  </p>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-600">
                    {r.cta}
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing teaser */}
        <section className="container py-20">
          <div className="overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-brand-500/5 via-card to-card p-8 sm:p-12">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                Simple plans that scale with you
              </h2>
              <p className="mt-4 text-muted-foreground">
                Start free, grow into team and enterprise tiers with SSO,
                priority support, and higher limits.
              </p>
              <Button size="lg" className="mt-8" asChild>
                <Link href="/pricing">
                  Compare plans
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="border-t border-border bg-muted/30">
          <div className="container py-20 text-center">
            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
              See an agent answer from your docs — live
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              The demo runs a real agent grounded in a sample help center. Ask
              it anything and watch it cite its sources.
            </p>
            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <Button size="lg" asChild>
                <Link href="/demo">
                  Launch live demo
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/pricing">View pricing</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
