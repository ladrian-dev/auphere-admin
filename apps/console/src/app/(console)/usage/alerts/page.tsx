import { redirect } from "next/navigation";

import { PageHeader, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { UsageAlertsForm } from "./form";

export const metadata = { title: "Alertas de consumo" };

export default async function UsageAlertsPage() {
  const principal = await requirePrincipal("/usage/alerts");
  if (!can(principal.role, "usage:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const alerts = await backendFor(principal).usageAlerts();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <>
      <PageHeader eyebrow={t("nav.group.operate")} title={t("hu.alerts.title")} description={t("hu.alerts.description")} />
      <p className="text-sm text-muted-foreground">
        {t("hu.alerts.status", {
          used: n(alerts.month_units),
          percent: alerts.percent != null ? t("hu.alerts.status.percent", { percent: n(alerts.percent) }) : "",
        })}
      </p>
      <UsageAlertsForm initial={alerts} canManage={can(principal.role, "usage:manage")} />
    </>
  );
}
