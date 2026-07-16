"use client";

import * as React from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useNotificationStore, type Toast, type ToastType } from "@/store/notification.store";
import { cn } from "@/lib/utils";

/** Visual treatment per toast type. */
const toastStyles: Record<
  ToastType,
  { container: string; icon: React.ReactNode }
> = {
  success: {
    container: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    icon: <CheckCircle2 className="h-5 w-5 text-emerald-500" />,
  },
  error: {
    container: "border-destructive/40 bg-destructive/10 text-destructive",
    icon: <XCircle className="h-5 w-5 text-destructive" />,
  },
  info: {
    container: "border-primary/40 bg-primary/10 text-foreground",
    icon: <Info className="h-5 w-5 text-primary" />,
  },
};

const AUTO_DISMISS_MS = 5000;

function ToastItem({ toast }: { toast: Toast }) {
  const removeToast = useNotificationStore((s) => s.removeToast);
  const style = toastStyles[toast.type];

  React.useEffect(() => {
    const t = setTimeout(() => removeToast(toast.id), AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [toast.id, removeToast]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-auto flex w-full items-start gap-3 rounded-lg border p-4 shadow-lg backdrop-blur-sm",
        "animate-in slide-in-from-right-4",
        style.container,
      )}
    >
      <div className="mt-0.5 shrink-0">{style.icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{toast.title}</p>
        {toast.message && (
          <p className="mt-0.5 break-words text-sm opacity-90">{toast.message}</p>
        )}
      </div>
      <button
        type="button"
        onClick={() => removeToast(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 rounded-sm opacity-60 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/**
 * Toast viewport. Mounted once at the app root (see app/providers.tsx) and
 * renders the current notification-store toasts in the bottom-right corner.
 */
export function Toaster() {
  const toasts = useNotificationStore((s) => s.toasts);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

export default Toaster;
