import { DashboardShell } from "@/components/layout/dashboard-shell";

/** Layout for all protected, authenticated pages. */
export default function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <DashboardShell>{children}</DashboardShell>;
}
