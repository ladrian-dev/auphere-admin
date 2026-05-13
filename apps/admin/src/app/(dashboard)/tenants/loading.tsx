import { HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function TenantsLoading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <div className="h-4 w-20 animate-pulse rounded bg-muted" />
        <div className="h-4 w-20 animate-pulse rounded bg-muted" />
      </div>
      <TableSkeleton rows={5} columns={5} />
    </>
  );
}
