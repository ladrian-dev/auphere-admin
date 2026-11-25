import { CardSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

/** Spec 077: the shape of «Envío por API» while it reads — keys, the call, the sends. */
export default function TenantApiLoading() {
  return (
    <div className="flex flex-col gap-8">
      <CardSkeleton lines={3} />
      <CardSkeleton lines={6} />
      <TableSkeleton />
    </div>
  );
}
