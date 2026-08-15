import { CardSkeleton, HeaderSkeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="grid gap-4 md:grid-cols-3">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    </>
  );
}
