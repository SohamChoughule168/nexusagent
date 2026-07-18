import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Building2,
  Users,
} from "lucide-react";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Demo request received",
  description: "Thanks — your NexusAgent demo request has been received.",
  robots: { index: false, follow: false },
};

type SearchParams = Promise<{
  name?: string;
  company?: string;
  team?: string;
  date?: string;
}>;

export default async function BookDemoConfirmationPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const name = params.name?.trim();
  const company = params.company?.trim();
  const team = params.team?.trim();
  const date = params.date?.trim();

  const summary = [
    company && { icon: Building2, label: "Company", value: company },
    team && { icon: Users, label: "Team size", value: `${team} employees` },
    date && {
      icon: CalendarClock,
      label: "Preferred date",
      value: formatDate(date),
    },
  ].filter(Boolean) as { icon: typeof Building2; label: string; value: string }[];

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        <section className="container flex flex-col items-center py-16 text-center">
          <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
            <CheckCircle2 className="h-7 w-7" />
          </div>
          <h1 className="text-balance text-3xl font-extrabold tracking-tight sm:text-4xl">
            {name ? `Thanks, ${name}` : "Demo request received"}
          </h1>
          <p className="mx-auto mt-3 max-w-md text-muted-foreground">
            We&apos;ve got your request and will email you within one business
            day to confirm a time that works.
          </p>

          {summary.length > 0 && (
            <div className="mt-8 w-full max-w-md space-y-3 text-left">
              {summary.map(({ icon: Icon, label, value }) => (
                <div
                  key={label}
                  className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3"
                >
                  <Icon className="h-4 w-4 shrink-0 text-brand-600" />
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="truncate text-sm font-medium">{value}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Button asChild className="mt-8">
            <Link href="/">
              Back to site
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

/** Format an ISO date (yyyy-mm-dd) for display; fall back to raw string. */
function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
