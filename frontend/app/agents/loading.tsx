import { LoadingState } from "@/components/ui/loading-state";

export default function AgentsLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <LoadingState label="Loading agents..." />
    </div>
  );
}
