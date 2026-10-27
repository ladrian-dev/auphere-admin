import { HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function CertificationsLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={5} columns={7} />
      <TableSkeleton rows={3} columns={7} />
    </>
  );
}
