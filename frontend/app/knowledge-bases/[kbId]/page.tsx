import { KnowledgeBaseDetail } from "@/features/knowledge-base/components/knowledge-base-detail";

export const metadata = {
  title: "Knowledge Base",
};

/** Knowledge base detail: documents, upload, and processing. */
export default async function KnowledgeBaseDetailPage({
  params,
}: {
  params: Promise<{ kbId: string }>;
}) {
  const { kbId } = await params;
  return <KnowledgeBaseDetail kbId={kbId} />;
}
