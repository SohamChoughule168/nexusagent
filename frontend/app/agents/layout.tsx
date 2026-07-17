import { DashboardShell } from "@/components/layout/dashboard-shell";

/** Layout for the Agent Builder module — reuses the authenticated app shell. */
export default function AgentsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <DashboardShell>{children}</DashboardShell>;
}
