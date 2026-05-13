import { Skeleton } from "@/components/ui/skeleton";

export default function AgentLoading() {
  return (
    <div className="grid gap-6">
      <div className="rounded-md border border-border bg-card p-6 grid gap-4">
        <div className="flex items-center justify-between">
          <div className="grid gap-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-6 w-72" />
          </div>
          <Skeleton className="h-9 w-40" />
        </div>
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <Skeleton className="h-[400px] w-full" />
          <div className="grid gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
