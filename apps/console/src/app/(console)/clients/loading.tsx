import { HeaderSkeleton, TableSkeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={6} columns={5} />
    </>
  );
}
