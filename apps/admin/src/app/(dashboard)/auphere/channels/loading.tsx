import { HeaderSkeleton, Skeleton } from "@nexus/ui";

import { NumbersTableSkeleton } from "./numbers-table";

/**
 * Spec 059 (6.1): the page as it will be drawn — the header, the table with
 * its own six columns, and the line that shows or hides the deactivated ones.
 */
export default function AuphereNumbersLoading() {
  return (
    <>
      <HeaderSkeleton label="Cargando" />
      <div className="flex flex-col gap-4">
        <NumbersTableSkeleton />
        <Skeleton className="h-5 w-48" />
      </div>
    </>
  );
}
