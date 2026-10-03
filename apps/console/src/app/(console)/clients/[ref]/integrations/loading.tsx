import { CardSkeleton, Skeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <CardSkeleton lines={3} />
      <CardSkeleton lines={3} />
      <CardSkeleton lines={3} />
    </div>
  );
}
