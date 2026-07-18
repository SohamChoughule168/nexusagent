"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { pageView } from "@/lib/analytics";

/**
 * Fires a `pageView` analytics event whenever the route changes. Mounted once
 * near the app root. The analytics layer is a no-op until a real provider is
 * configured, so this is safe to keep in production.
 */
export function RouteTracker() {
  const pathname = usePathname();

  React.useEffect(() => {
    if (pathname) pageView(pathname);
  }, [pathname]);

  return null;
}

export default RouteTracker;
