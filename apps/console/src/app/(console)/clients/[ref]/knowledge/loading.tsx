import { CardSkeleton, Skeleton, TableSkeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-3 md:grid-cols-2">
        <CardSkeleton lines={3} />
        <CardSkeleton lines={2} />
      </div>
      <TableSkeleton rows={4} columns={6} />
    </div>
  );
}
