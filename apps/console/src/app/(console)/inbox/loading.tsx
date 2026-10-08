import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/** The Inbox while its first read is on the way: the real frame, the real widths. */
export default async function Loading() {
  const { t } = await getT();
  return (
    <div
      role="status"
      aria-label={t("inbox.list.loading")}
      className="flex h-[calc(100svh-8rem)] min-h-[32rem] flex-col overflow-hidden rounded-md border border-border bg-card"
    >
      <div className="border-b border-border px-4 py-2">
        <Skeleton className="h-6 w-40" />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="flex w-full flex-col gap-2 p-3 md:w-80 md:border-r md:border-border">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-7 w-3/4" />
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex items-start gap-3 py-2">
              <Skeleton className="size-10 shrink-0 rounded-full" />
              <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            </div>
          ))}
        </div>
        <div className="hidden flex-1 md:block" />
      </div>
    </div>
  );
}
