"use client";

import * as React from "react";

/**
 * Tracks the browser's online/offline state. Returns `true` when the user has
 * a network connection. Starts optimistic (`true`) and corrects after mount to
 * avoid a hydration flash.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = React.useState(true);

  React.useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}
