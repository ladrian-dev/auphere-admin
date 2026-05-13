import { CardSkeleton } from "@/components/skeletons/list-skeleton";

export default function TenantConnectorsLoading() {
  return (
    <div className="grid gap-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <CardSkeleton key={i} lines={3} />
      ))}
    </div>
  );
}
