import { redirect } from "next/navigation";

/**
 * Root route: send everyone to the dashboard. AuthGuard inside the dashboard
 * layout redirects unauthenticated users to /login.
 */
export default function RootPage() {
  redirect("/dashboard");
}
