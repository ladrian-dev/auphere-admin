import Link from "next/link";

import { Alert, AlertDescription, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Metric, StatusDot, formatNumber } from "@nexus/ui";

import { missingItems } from "@/components/clients/health";
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
  // Spec 016 (R2.1/R2.4): what is missing, each piece with the click that
  // fixes it. «Sin cupo» is its own line: it does not block «listo», but the
  // client is not answering, and the card must say both things.
  const items = missingItems(h, ref);
  const blocking = items.filter((m) => m.blocking);
  const outOfQuota = items.some((m) => m.key === "quota");
  const missingLabels = blocking.map((m) => t(m.label));
  const base = `/clients/${encodeURIComponent(ref)}`;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-3" id="setup">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <StatusDot tone={h.ready ? (outOfQuota ? "warning" : "positive") : "warning"} />
            {h.ready ? t("clients.detail.ready") : t("clients.detail.missing", { items: missingLabels.join(", ") })}
          </CardTitle>
          <CardDescription>
            {t("clients.detail.agent")}: {h.agent_version ? t("clients.detail.agentVersion", { v: h.agent_version }) : t("clients.detail.noAgent")} ·{" "}
            {t("clients.detail.whatsapp")}: {h.whatsapp_connected ? t("status.connected") : t("status.disconnected")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {outOfQuota ? (
            <Alert role="status" className="border-status-warning/40">
              <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>{t("clients.health.outOfQuota")}</span>
                {can(principal.role, "usage:write") ? (
                  <Link href={`/usage?client=${encodeURIComponent(ref)}`} className="font-medium underline underline-offset-4">
                    {t("clients.health.fix.quota")}
                  </Link>
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {blocking
              .filter((m) => m.href && can(principal.role, m.permission))
              .map((m) => (
                <Button key={m.key} variant="outline" size="sm" nativeButton={false} render={<Link href={m.href!} />}>
                  {t(m.fix)}
                </Button>
              ))}
            {h.ready && can(principal.role, "agents:write") ? (
              <Button variant="outline" size="sm" nativeButton={false} render={<Link href={`${base}/agent`} />}>
                {t("clients.tabs.agent")}
              </Button>
            ) : null}
            {/* Spec 017 R1.6 (paridad, fila 10): pausar, archivar y eliminar
                se mudaron al menú «Más» de la cabecera, que está en todas las
                pestañas. Dejarlos aquí además era ofrecer dos veces lo mismo
                en la misma pantalla. */}
          </div>
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
