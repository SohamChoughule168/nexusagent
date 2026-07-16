"use client";

import * as React from "react";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import { AuthProvider } from "@/providers/auth-provider";
import { Toaster } from "@/components/ui/toaster";

/**
 * App-wide client providers, composed once at the root layout.
 * Order matters: Theme/Auth context should wrap everything that consumes them.
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <QueryProvider>
        <AuthProvider>
          {children}
          <Toaster />
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
  );
}

export default AppProviders;
