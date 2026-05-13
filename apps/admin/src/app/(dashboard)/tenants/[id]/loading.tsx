import { CardSkeleton } from "@/components/skeletons/list-skeleton";

export default function TenantOverviewLoading() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <CardSkeleton lines={5} />
      <CardSkeleton lines={3} />
      <CardSkeleton lines={3} />
    </div>
  );
}
