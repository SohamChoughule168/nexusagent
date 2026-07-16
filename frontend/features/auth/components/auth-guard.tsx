"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { LoadingState } from "@/components/ui/loading-state";

export interface AuthGuardProps {
  children: React.ReactNode;
  /** Where to send unauthenticated users. */
  redirectTo?: string;
}

/**
 * Client-side route guard for protected pages. Reads auth state from the
 * Zustand store (which is rehydrated from localStorage by AuthProvider). Until
 * hydration completes we render a loading state to avoid a flash of the login
 * page for already-authenticated users.
 */
export function AuthGuard({
  children,
  redirectTo = "/login",
}: AuthGuardProps) {
  const { isAuthenticated, hasHydrated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [redirected, setRedirected] = React.useState(false);

  React.useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated && !redirected) {
      setRedirected(true);
      const next = encodeURIComponent(pathname || "/dashboard");
      router.replace(`${redirectTo}?redirect=${next}`);
    }
  }, [hasHydrated, isAuthenticated, redirected, redirectTo, pathname, router]);

  if (!hasHydrated || !isAuthenticated) {
    if (redirected) return null;
    return <LoadingState fullScreen label="Checking authentication..." />;
  }

  return <>{children}</>;
}

export default AuthGuard;
