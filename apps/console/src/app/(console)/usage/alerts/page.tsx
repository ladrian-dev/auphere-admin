import { redirect } from "next/navigation";

import { Card, CardContent, PageHeader, cn, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { UsageAlertsForm } from "./form";
import { pageTitle } from "@/i18n/metadata";
import { ShellBackButton } from "@/components/shell/shell-back-button";

export const generateMetadata = () => pageTitle("hu.alerts.title");

export default async function UsageAlertsPage() {
  const principal = await requirePartnerPrincipal("/usage/alerts");
  if (!can(principal.role, "usage:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const alerts = await backendFor(principal).usageAlerts();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <>
      <PageHeader size="display" back={<ShellBackButton />} title={t("hu.alerts.title")} description={t("hu.alerts.description")} />
      {/* Spec 047 (prototipo): una tarjeta de 620 px con «Este mes», la cifra, su
          barra (ámbar desde el 80 %) y el formulario debajo. */}
      <Card className="max-w-2xl" data-slot="usage-alerts">
        <CardContent className="grid min-w-0 gap-4">
          <div className="grid gap-2">
            <p className="text-xs text-muted-foreground">{t("proto.alerts.month")}</p>
            <p className="text-sm text-muted-foreground">
              <span className="text-lg font-semibold text-foreground tabular-nums">{t("proto.alerts.messages", { used: n(alerts.month_units) })}</span>
              {alerts.percent != null ? t("hu.alerts.status.percent", { percent: n(alerts.percent) }) : null}
            </p>
            {alerts.percent != null ? (
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span
                  className={cn("block h-full rounded-full", alerts.percent >= 80 ? "bg-status-warning" : "bg-primary")}
                  style={{ width: `${Math.min(100, Math.max(0, alerts.percent))}%` }}
                />
              </div>
            ) : null}
          </div>
          <UsageAlertsForm initial={alerts} canManage={can(principal.role, "usage:manage")} />
        </CardContent>
      </Card>
    </>
  );
}
