import { CardSkeleton } from "@nexus/ui";

export default function Loading() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <CardSkeleton />
      <CardSkeleton />
      <CardSkeleton />
    </div>
  );
}
