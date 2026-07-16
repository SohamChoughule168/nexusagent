import { KnowledgeBaseDashboard } from "@/features/knowledge-base/components/knowledge-base-dashboard";

export const metadata = {
  title: "Knowledge Bases",
};

/** Knowledge Base management dashboard (list, search, create, edit, delete). */
export default function KnowledgeBasesPage() {
  return <KnowledgeBaseDashboard />;
}
