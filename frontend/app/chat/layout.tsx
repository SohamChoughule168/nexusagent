import { DashboardShell } from "@/components/layout/dashboard-shell";

/** Layout for the Chat module — reuses the authenticated app shell. */
export default function ChatLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <DashboardShell>{children}</DashboardShell>;
}
