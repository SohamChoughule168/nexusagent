"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, LifeBuoy, RotateCw } from "lucide-react";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { Button } from "@/components/ui/button";

/**
 * Global error boundary. Rendered by Next.js when a route segment throws.
 * Shows a friendly message, the error digest (for support), a retry that
 * resets the segment, and a link back to safety.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // In production, forward to an error-reporting service here.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main
        id="main-content"
        className="flex flex-1 items-center justify-center bg-muted/30 px-4 py-16"
      >
        <div className="flex max-w-md flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-xl font-semibold">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            An unexpected error occurred on our end. You can retry, or head back
            to the homepage. If it keeps happening, our team can help.
          </p>

          {error.digest && (
            <p className="mt-3 rounded-md border border-border bg-card px-3 py-1.5 font-mono text-xs text-muted-foreground">
              Reference: {error.digest}
            </p>
          )}

          <div className="mt-6 flex flex-col gap-2 sm:flex-row">
            <Button onClick={reset}>
              <RotateCw className="h-4 w-4" />
              Try again
            </Button>
            <Button asChild variant="outline">
              <Link href="/">Go to homepage</Link>
            </Button>
            <Button asChild variant="ghost">
              <Link href="/contact">
                <LifeBuoy className="h-4 w-4" />
                Contact support
              </Link>
            </Button>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
