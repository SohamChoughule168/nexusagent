"use client";

import { WifiOff } from "lucide-react";
import { useOnlineStatus } from "@/hooks/use-online-status";

/**
 * Fixed top banner shown when the browser goes offline. Self-contained: reads
 * `useOnlineStatus` and renders nothing while online.
 */
export function OfflineBanner() {
  const online = useOnlineStatus();

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-[110] flex items-center justify-center gap-2 bg-destructive px-4 py-2 text-center text-sm font-medium text-destructive-foreground"
    >
      <WifiOff className="h-4 w-4" />
      You&apos;re offline — some features may be unavailable. We&apos;ll
      reconnect automatically.
    </div>
  );
}

export default OfflineBanner;
