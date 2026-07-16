import { DashboardShell } from "@/components/layout/dashboard-shell";

/** Layout for the Knowledge Base module — reuses the authenticated app shell. */
export default function KnowledgeBasesLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <DashboardShell>{children}</DashboardShell>;
}
