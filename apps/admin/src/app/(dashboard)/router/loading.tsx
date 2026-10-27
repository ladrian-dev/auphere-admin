import { CardSkeleton, HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function RouterLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={7} columns={7} />
      <CardSkeleton lines={3} />
    </>
  );
}
