import { CardSkeleton, HeaderSkeleton } from "@/components/skeletons/list-skeleton";

export default function GlobalConnectorsLoading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <CardSkeleton key={i} lines={2} />
        ))}
      </div>
    </>
  );
}
