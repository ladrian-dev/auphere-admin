import { Skeleton } from "@/components/ui/skeleton";

export default function ConversationDetailLoading() {
  return (
    <div className="grid gap-6">
      <div className="rounded-md border border-border bg-card p-6 grid gap-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-6 w-72" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <div className="rounded-md border border-border bg-card p-6 grid gap-3">
        <Skeleton className="h-4 w-32" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-md border border-border px-3 py-2 grid gap-2"
          >
            <Skeleton className="h-3 w-1/4" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}
