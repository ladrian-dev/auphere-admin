import { CardSkeleton, HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function BuilderEvalLoading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <CardSkeleton key={i} lines={2} />
        ))}
      </div>
      <TableSkeleton rows={5} columns={5} />
    </>
  );
}
