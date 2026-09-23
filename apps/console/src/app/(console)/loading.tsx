import { CardSkeleton, HeaderSkeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

export default async function Loading() {
  const { t } = await getT();
  return (
    <>
      <HeaderSkeleton label={t("ui.loading")} />
      <div className="grid gap-4 md:grid-cols-3">
        <CardSkeleton label={t("ui.loading")} />
        <CardSkeleton label={t("ui.loading")} />
        <CardSkeleton label={t("ui.loading")} />
      </div>
    </>
  );
}
