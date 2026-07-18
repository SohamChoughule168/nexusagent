import Link from "next/link";
import { ArrowLeft, FileQuestion, Mail, Search } from "lucide-react";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main
        id="main-content"
        className="flex flex-1 items-center justify-center bg-muted/30 px-4 py-16"
      >
        <EmptyState
          icon={<FileQuestion className="h-10 w-10" />}
          title="404 — Page not found"
          description="The page you're looking for doesn't exist or may have moved. Try searching the docs, or head back home."
          action={
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button asChild>
                <Link href="/">
                  <ArrowLeft className="h-4 w-4" />
                  Back to home
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/#docs">
                  <Search className="h-4 w-4" />
                  Search docs
                </Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/contact">
                  <Mail className="h-4 w-4" />
                  Contact us
                </Link>
              </Button>
            </div>
          }
        />
      </main>
      <SiteFooter />
    </div>
  );
}
