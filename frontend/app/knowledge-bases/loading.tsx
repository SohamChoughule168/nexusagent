import { Skeleton } from "@/components/ui/skeleton";

export default function KnowledgeBasesLoading() {
  return (
    <div
      className="space-y-6"
      aria-busy="true"
      aria-label="Loading knowledge bases"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-52" />
          <Skeleton className="h-4 w-72" />
        </div>
        <Skeleton className="h-10 w-44" />
      </div>

      <Skeleton className="h-10 w-full max-w-sm" />

      <div className="rounded-lg border bg-card">
        <div className="border-b px-4 py-3">
          <Skeleton className="h-4 w-24" />
        </div>
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center justify-between gap-4 border-b px-4 py-4 last:border-b-0"
          >
            <Skeleton className="h-4 w-40" />
            <Skeleton className="hidden h-4 w-48 md:block" />
            <Skeleton className="hidden h-4 w-24 sm:block" />
            <Skeleton className="h-8 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}
