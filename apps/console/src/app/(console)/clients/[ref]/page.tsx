import Link from "next/link";

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Metric, StatusDot, formatNumber } from "@nexus/ui";

import { ClientLifecycleActions } from "@/components/clients/lifecycle-actions";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { getClientCached } from "./data";

export default async function ClientOverviewPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const [client, stats] = await Promise.all([
    getClientCached(principal, ref),
    can(principal.role, "conversations:read") ? api.conversationStats(ref, 30).catch(() => null) : null,
  ]);
  const h = client.health;
  const missingLabels = h.missing.map((m) => t(`clients.detail.missing.${m}` as "clients.detail.missing.agent"));
  const base = `/clients/${encodeURIComponent(ref)}`;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <StatusDot tone={h.ready ? "positive" : "warning"} />
            {h.ready ? t("clients.detail.ready") : t("clients.detail.missing", { items: missingLabels.join(", ") })}
          </CardTitle>
          <CardDescription>
            {t("clients.detail.agent")}: {h.agent_version ? t("clients.detail.agentVersion", { v: h.agent_version }) : t("clients.detail.noAgent")} ·{" "}
            {t("clients.detail.whatsapp")}: {h.whatsapp_connected ? t("status.connected") : t("status.disconnected")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {can(principal.role, "agents:write") ? (
            <Button variant="outline" size="sm" nativeButton={false} render={<Link href={`${base}/agent`} />}>
              {t("clients.tabs.agent")}
            </Button>
          ) : null}
          {can(principal.role, "clients:write") ? <ClientLifecycleActions refId={ref} status={client.status} name={client.name} canDelete={can(principal.role, "clients:delete")} /> : null}
        </CardContent>
      </Card>
      {stats ? (
        <>
          <Metric label={t("conv.stats.total")} value={formatNumber(stats.conversations, locale)} href={`${base}/conversations`} />
          <Metric label={t("conv.stats.escalated")} value={formatNumber(stats.escalated, locale)} href={`${base}/conversations?escalated=true`} />
          <Metric label={t("conv.stats.failed")} value={formatNumber(stats.failed_messages, locale)} href={`${base}/conversations?with_errors=true`} />
        </>
      ) : null}
    </div>
  );
}
