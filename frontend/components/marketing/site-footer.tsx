import * as React from "react";
import Link from "next/link";
import { Logo } from "@/components/marketing/logo";

const FOOTER_COLUMNS = [
  {
    title: "Product",
    links: [
      { href: "/#features", label: "Features" },
      { href: "/#how-it-works", label: "How it works" },
      { href: "/pricing", label: "Pricing" },
      { href: "/demo", label: "Live demo" },
    ],
  },
  {
    title: "Resources",
    links: [
      { href: "/#docs", label: "Documentation" },
      { href: "/login", label: "Sign in" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "/#use-cases", label: "Use cases" },
      { href: "/pricing", label: "Plans" },
    ],
  },
];

/** Public marketing footer, shared across landing / pricing / demo. */
export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="container py-12">
        <div className="grid gap-10 md:grid-cols-[1.5fr_repeat(3,1fr)]">
          <div className="space-y-3">
            <Logo />
            <p className="max-w-xs text-sm text-muted-foreground">
              The AI agent platform that knows your business. Build, ground, and
              orchestrate autonomous agents on your own knowledge.
            </p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <div key={col.title} className="space-y-3">
              <h4 className="text-sm font-semibold text-foreground">
                {col.title}
              </h4>
              <ul className="space-y-2">
                {col.links.map((link) => (
                  <li key={link.href + link.label}>
                    <Link
                      href={link.href}
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col items-start justify-between gap-3 border-t border-border pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center">
          <p>© {new Date().getFullYear()} NexusAgent. All rights reserved.</p>
          <p>Proprietary software — not for redistribution.</p>
        </div>
      </div>
    </footer>
  );
}

export default SiteFooter;
