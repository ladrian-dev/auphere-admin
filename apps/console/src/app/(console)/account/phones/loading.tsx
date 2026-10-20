import { Skeleton } from "@nexus/ui";

/** The shape of «Tus teléfonos» while it loads: the header and two rows, same heights. */
export default function Loading() {
  return (
    <div aria-busy="true" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-full max-w-prose" />
      </div>
      <div className="flex flex-col divide-y divide-border rounded-md border border-border bg-card">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-4">
            <Skeleton className="size-10 shrink-0 rounded-md" />
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-56 max-w-full" />
            </div>
            <Skeleton className="h-8 w-28 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}
