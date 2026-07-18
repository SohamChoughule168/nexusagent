import { Skeleton } from "@/components/ui/skeleton";

export default function KnowledgeBaseDetailLoading() {
  return (
    <div
      className="space-y-6"
      aria-busy="true"
      aria-label="Loading knowledge base"
    >
      <div className="flex items-center gap-3">
        <Skeleton className="h-9 w-9 rounded-md" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-4 w-72" />
        </div>
        <Skeleton className="h-9 w-20" />
        <Skeleton className="h-9 w-20" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3 rounded-xl border border-border bg-card p-5">
          <Skeleton className="h-4 w-40" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-32" />
                </div>
              </div>
              <Skeleton className="h-6 w-20 rounded-full" />
            </div>
          ))}
        </div>

        <div className="space-y-3 rounded-xl border border-border bg-card p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-9 w-full" />
        </div>
      </div>
    </div>
  );
}
