import { CardSkeleton, Skeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
      <div className="flex flex-col gap-4">
        <CardSkeleton lines={2} />
        <CardSkeleton />
      </div>
    </div>
  );
}
