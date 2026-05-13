import { TableSkeleton } from "@/components/skeletons/list-skeleton";
import { Skeleton } from "@/components/ui/skeleton";

export default function ConversationsLoading() {
  return (
    <div className="grid gap-6">
      <div className="rounded-md border border-border bg-card p-6 grid gap-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <TableSkeleton rows={6} columns={5} />
      </div>
    </div>
  );
}
