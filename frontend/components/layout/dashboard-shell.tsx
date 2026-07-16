"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/layout/sidebar";
import { TopNav } from "@/components/layout/top-nav";
import { AuthGuard } from "@/features/auth/components/auth-guard";

export interface DashboardShellProps {
  children: React.ReactNode;
}

/**
 * Authenticated application shell: sidebar (desktop) + top nav + content area.
 * Wrapped in AuthGuard so unauthenticated visitors are redirected to /login.
 * On mobile the sidebar becomes a slide-in drawer toggled from the top nav.
 */
export function DashboardShell({ children }: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = React.useState(false);

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-background">
        {/* Desktop sidebar */}
        <div className="hidden md:block">
          <Sidebar />
        </div>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
              aria-hidden="true"
            />
            <div
              className={cn(
                "absolute left-0 top-0 h-full animate-in slide-in-from-left",
              )}
            >
              <Sidebar />
            </div>
          </div>
        )}

        <div className="flex flex-1 flex-col overflow-hidden">
          <TopNav onMenuClick={() => setMobileOpen((o) => !o)} />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}

export default DashboardShell;
