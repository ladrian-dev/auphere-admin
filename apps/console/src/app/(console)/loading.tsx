import { headers } from "next/headers";

import { LitePanelSkeleton } from "@/components/lite/lite-skeletons";
import { PageSkeleton } from "@/components/shell/page-skeleton";
import { getT } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

/**
 * The console's loading state for every page without its own. Spec 045
 * (R6.5): the client's Panel loads with the Panel's shape; the partner's
 * home, and anything else, keep the plain one. It only reads who is asking
 * —the layout already resolved it, so it is cached— and never redirects:
 * a redirect thrown under `loading.tsx` broke Next's Router (T111).
 */
export default async function Loading() {
  const resolution = await resolvePrincipal();
  const principal = resolution.kind === "ok" ? resolution.principal : null;
  const { t } = await getT(principal?.locale);
  if (principal?.kind === "client" && (await headers()).get("x-pathname") === "/") {
    return <LitePanelSkeleton t={t} modules={principal.modules} />;
  }
  return <PageSkeleton label={t("ui.loading")} />;
}
