import { HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function ModelsLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={6} columns={6} />
    </>
  );
}
