import { CardSkeleton } from "@/components/skeletons/list-skeleton";

export default function IsolationLoading() {
  return (
    <div className="grid gap-6">
      <CardSkeleton lines={3} />
      <CardSkeleton lines={7} />
    </div>
  );
}
