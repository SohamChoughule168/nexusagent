import { LoadingState } from "@/components/ui/loading-state";

export default function KnowledgeBasesLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <LoadingState label="Loading knowledge bases..." />
    </div>
  );
}
