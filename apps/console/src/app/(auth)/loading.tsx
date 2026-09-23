import { Skeleton } from "@nexus/ui";

/** The access pages are one heading and a short form; the skeleton keeps
 * that shape so the page does not jump when it arrives. */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-10 w-2/3" />
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    </div>
  );
}
