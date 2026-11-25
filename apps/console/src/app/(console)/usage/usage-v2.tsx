import Link from "next/link";

import { Bell } from "lucide-react";

import { Button, Callout, Card, CardContent, ErrorState, PageHeader } from "@nexus/ui";

import { MONEY_CODES, attentionKey } from "@/components/attention/attention-model";
import { AttentionRow } from "@/components/attention/attention-row";
import { MetaMark } from "@/components/money/meta-mark";
import { migrationPending, moneyText, parseDays } from "@/components/money/money-model";
import { SpendByDay, SpendFilters } from "@/components/money/spend-by-day";
import { UsageClientsTable } from "@/components/money/usage-clients-table";
import { UsageDetailPanel } from "@/components/money/usage-detail";
import { UsageFigure } from "@/components/money/usage-figure";
import { SeedRequested } from "@/components/money/request-balance";
import { periodLabel } from "@/components/clients/v2/client-v2-model";
import { getT } from "@/i18n/server";
import { backendFor, callFor } from "@/lib/backend";
import { moneyApi } from "@/lib/backend/money";
import { can, type PartnerPrincipal } from "@/lib/principal";

import { BuyDialog } from "./buy-dialog";

type Search = { days?: string; client?: string; line?: string };

/**
 * Consumo con la consola nueva (spec 047, T159; requisitos 45 y 46), en el orden
 * de la demo aprobada — spec 072 (4.1), en la moneda de la cuenta del partner:
 *
 * 1. «Gasto por día · últimos N días»: 7, 30 o 90 días en la cápsula y el
 *    cliente al lado, sin el desplegable de partida (D3).
 * 2. Las cuatro cifras: «Saldo disponible», «En bolsas de clientes», «Gasto del
 *    mes» (lo que gastan las bolsas de sus clientes, con su periodo y su
 *    proyección) y «Mensajes de Meta», con su marca y sin «≈» (4.3).
 * 3. La tabla por cliente, con «Cambiar saldo», «Mover» y «Ver su gasto».
 * 4. Los avisos de dinero de la 071, cada uno con su acción.
 * 5. El detalle técnico, plegado, con Companion y teammates (D2) y «Descargar CSV».
 *
 * Las tarjetas de «quién paga qué» ya no están (4.4): cada cifra lo dice, y el
 * tope de construcción vive en la línea del Panel y en su aviso. Todas las
 * cifras salen del libro (46.7): si una lectura falla, su bloque lo dice y no
 * pinta ceros. Si el partner aún reparte con los topes de antes, lo primero es
 * «Repartir tu saldo en bolsas» (55.3).
 */
export async function PartnerUsageV2({ principal, searchParams }: { principal: PartnerPrincipal; searchParams: Search }) {
  const { t } = await getT(principal.locale);
  const days = parseDays(searchParams.days);
  const client = (searchParams.client ?? "").slice(0, 255);
  const canWrite = can(principal.role, "usage:write");
  const api = moneyApi(callFor(principal));
  const [summary, daily, detail, migration, bags, attention] = await Promise.all([
    api.usageSummary().catch(() => null),
    api.usageDaily({ days, client: client || undefined }).catch(() => null),
    api.usageDetail({ days, client: client || undefined }).catch(() => null),
    api.getMigration().catch(() => null),
    canWrite ? null : api.listBags().catch(() => null),
    // Spec 071 (5): los avisos de dinero salen de la misma lista del Panel y de la campana.
    backendFor(principal).attention().catch(() => null),
  ]);
  const notices = (attention?.items ?? []).filter((row) => MONEY_CODES.has(row.code));
  const low = new Set(notices.filter((row) => row.code === "low_balance" && row.external_client_ref).map((row) => row.external_client_ref as string));
  const pending = migrationPending(migration);
  const clients = summary?.clients ?? [];
  const names = Object.fromEntries(clients.map((c) => [c.ref, c.name ?? c.ref]));
  const options = clients.map((c) => ({ ref: c.ref, name: c.name ?? c.ref }));
  const currency = summary?.currency ?? daily?.currency ?? "USD";
  const meta = summary?.lines.find((l) => l.line === "meta") ?? null;
  const companion = summary?.lines.find((l) => l.line === "companion") ?? null;
  const withBag = clients.filter((c) => c.bag).length;
  const now = new Date();
  const month = periodLabel(
    `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`,
    new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).toISOString().slice(0, 10),
    now,
    principal.locale,
  );

  return (
    <>
      <PageHeader
        size="display"
        title={t("usage.title")}
        description={t("usage.description")}
        actions={
          <>
            <Button nativeButton={false} variant="outline" render={<Link href="/usage/alerts" />}>
              <Bell aria-hidden="true" />
              {t("hu.usage.alerts.link")}
            </Button>
            {can(principal.role, "billing:manage") ? <BuyDialog accountCurrency={summary?.currency ?? null} /> : null}
          </>
        }
      />

      {bags ? <SeedRequested items={bags} /> : null}
      {pending ? (
        <Callout
          tone="info"
          title={t("money.migration.title")}
          action={
            <Button size="sm" nativeButton={false} render={<Link href="/usage/repartir" />}>
              {t("money.migration.cta")}
            </Button>
          }
        >
          {t("money.migration.banner")}
        </Callout>
      ) : null}

      <Card id="gasto" data-slot="usage-spend" className="scroll-mt-24">
        <CardContent className="grid min-w-0 gap-4">
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">{t("money.chart.titleDays", { days })}</h2>
            <SpendFilters days={days} client={client} clients={options} />
          </div>
          <SpendByDay daily={daily} line={null} currency={currency} />
        </CardContent>
      </Card>

      {!summary ? (
        <ErrorState title={t("money.usage.error")} />
      ) : (
        <>
          {/* Las cuatro cifras de la demo (spec 072, 4.3): sin icono, cifra grande y una nota. */}
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label={t("money.figures")} data-slot="usage-figures">
            <UsageFigure label={t("money.figure.available")} value={moneyText(summary.available, "down")} hint={t("money.figure.available.hint")} />
            <UsageFigure
              label={t("money.figure.inBags")}
              value={`${summary.in_bags_approx ? `${t("money.approxPrefix")} ` : ""}${moneyText(summary.in_bags, "down")}`}
              hint={`${t(withBag === 1 ? "money.figure.inBags.clients.one" : "money.figure.inBags.clients", { n: withBag })}${summary.in_bags_approx ? `. ${t("money.figure.inBags.otherCurrency")}` : ""}`}
            />
            <UsageFigure
              label={t("money.figure.month")}
              value={moneyText(summary.month_spend)}
              hint={`${month} · ${t("money.figure.month.hint", { amount: moneyText(summary.projected) })}`}
            />
            <UsageFigure label={t("money.figure.meta")} mark={<MetaMark />} value={meta ? moneyText(meta.amount) : "—"} hint={t("money.figure.meta.hint")} />
          </section>

          <Card data-slot="usage-balance">
            <CardContent className="grid min-w-0 gap-4">
              <div className="grid gap-1">
                <h2 className="text-base font-semibold">{t("money.table.title")}</h2>
                <p className="text-sm text-pretty text-muted-foreground">{t("money.table.description")}</p>
              </div>
              <UsageClientsTable clients={clients} canWrite={canWrite} days={days} low={low} />
            </CardContent>
          </Card>
        </>
      )}

      {/* Spec 071 (5.1), como la demo aprobada: los avisos de dinero, cada uno con su acción. */}
      {notices.length ? (
        <Card data-slot="usage-notices">
          <CardContent className="grid min-w-0 gap-1">
            <h2 className="text-base font-semibold">{t("att.usage.title")}</h2>
            <ul className="divide-y divide-border">
              {notices.map((row) => (
                <AttentionRow key={attentionKey(row)} row={row} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <UsageDetailPanel detail={detail} names={names} days={days} client={client} account={companion?.amount ?? null} />
    </>
  );
}
