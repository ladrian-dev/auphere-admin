import { HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function SectorTestsLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={12} columns={3} />
    </>
  );
}
