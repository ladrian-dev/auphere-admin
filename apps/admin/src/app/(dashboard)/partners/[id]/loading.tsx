import { CardSkeleton } from "@/components/skeletons/list-skeleton";

export default function PartnerDetailLoading() {
  return (
    <div className="grid gap-6">
      <CardSkeleton lines={5} />
    </div>
  );
}
