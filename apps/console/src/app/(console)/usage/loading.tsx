import { LiteUsageSkeleton } from "@/components/lite/lite-skeletons";
import { PageSkeleton } from "@/components/shell/page-skeleton";
import { getT } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Consumo while it loads (spec 045, R6.5): the client's with its own shape
 * —the balance first—; the partner's keeps the plain skeleton it had from the
 * console's root. Reads who is asking (cached by the layout), never redirects.
 */
export default async function Loading() {
  const resolution = await resolvePrincipal();
  const principal = resolution.kind === "ok" ? resolution.principal : null;
  const { t } = await getT(principal?.locale);
  if (principal?.kind === "client") return <LiteUsageSkeleton t={t} />;
  return <PageSkeleton label={t("ui.loading")} />;
}
