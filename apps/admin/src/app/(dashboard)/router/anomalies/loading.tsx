import { HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function RouterAnomaliesLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={5} columns={5} />
    </>
  );
}
