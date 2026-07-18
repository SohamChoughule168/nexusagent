import * as React from "react";

/**
 * Per-navigation wrapper. App Router remounts this on every route change, so a
 * short fade gives a smooth transition without layout shift.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="animate-in fade-in-0 duration-200">{children}</div>;
}
