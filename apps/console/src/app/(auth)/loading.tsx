import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/** The access pages are one heading and a short form; the skeleton keeps
 * that shape so the page does not jump when it arrives. */
export default async function Loading() {
  const { t } = await getT();
  return (
    <div className="flex flex-col gap-6" aria-busy="true" role="status" aria-label={t("ui.loading")}>
      <Skeleton className="h-10 w-2/3" />
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    </div>
  );
}
