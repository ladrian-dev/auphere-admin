import { HeaderSkeleton, Skeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="flex max-w-3xl flex-col gap-6" aria-busy="true">
        <div className="flex gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-7 w-24 rounded-full" />
          ))}
        </div>
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </>
  );
}
