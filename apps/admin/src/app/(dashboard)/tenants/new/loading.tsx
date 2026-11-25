import { CardSkeleton, HeaderSkeleton } from "@/components/skeletons/list-skeleton";

/**
 * Spec 077: the page now waits for the partner list. Its own skeleton, shaped
 * like the form, so the client list's table does not flash in its place.
 */
export default function NewTenantLoading() {
  return (
    <>
      <HeaderSkeleton />
      <div className="max-w-3xl">
        <CardSkeleton lines={8} />
      </div>
    </>
  );
}
