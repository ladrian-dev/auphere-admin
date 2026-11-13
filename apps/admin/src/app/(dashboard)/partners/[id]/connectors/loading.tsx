import { TableSkeleton } from "@/components/skeletons/list-skeleton";

/** Spec 060: la tabla de conectores del partner, con sus cuatro columnas. */
export default function PartnerConnectorsLoading() {
  return <TableSkeleton rows={5} columns={4} />;
}
