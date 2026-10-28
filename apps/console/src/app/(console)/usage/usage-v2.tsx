import Link from "next/link";

import { CircleDollarSign, Users, Wallet as WalletIcon } from "lucide-react";

import { Button, Callout, ErrorState, Metric, PageHeader, Section } from "@nexus/ui";

import { migrationPending, moneyText, parseDays, parseLine } from "@/components/money/money-model";
import { SpendByDay, SpendFilters } from "@/components/money/spend-by-day";
import { UsageClientsTable } from "@/components/money/usage-clients-table";
import { UsageDetailPanel } from "@/components/money/usage-detail";
import { UsageLines } from "@/components/money/usage-lines";
import { SeedRequested } from "@/components/money/request-balance";
import { getT } from "@/i18n/server";
import { callFor } from "@/lib/backend";
import { moneyApi } from "@/lib/backend/money";
import { can, type PartnerPrincipal } from "@/lib/principal";

import { BuyDialog } from "./buy-dialog";

type Search = { days?: string; client?: string; line?: string };

/**
 * Consumo con la consola nueva (spec 047, T159; requisitos 45 y 46), en la moneda
 * de la cuenta del partner:
 *
 * 1. Las tres cifras: «Saldo disponible» (lo que se puede asignar, sin el pool
 *    incluido), «En bolsas de clientes» («aprox.» si hay bolsas en otra moneda)
 *    y «Gasto del mes» con su proyección al ritmo de 7 días.
 * 2. La tabla por cliente, con «Cambiar saldo», «Mover» y «Ver su gasto».
 * 3. «Gasto por día»: la gráfica de bloques de 7, 30 o 90 días, por cliente y
 *    por partida, con su tabla para lectores de pantalla.
 * 4. Las cuatro partidas con quién paga cada una, y la de construcción con su
 *    tope y «Pedir ampliación».
 * 5. El detalle técnico, plegado, y «Descargar CSV».
 *
 * Todas las cifras salen del libro (46.7): si una lectura falla, su bloque lo
 * dice y no pinta ceros. Si el partner aún reparte con los topes de antes, lo
 * primero es «Repartir tu saldo en bolsas» (55.3).
 */
export async function PartnerUsageV2({ principal, searchParams }: { principal: PartnerPrincipal; searchParams: Search }) {
  const { t } = await getT(principal.locale);
  const days = parseDays(searchParams.days);
  const line = parseLine(searchParams.line);
  const client = (searchParams.client ?? "").slice(0, 255);
  const canWrite = can(principal.role, "usage:write");
  const api = moneyApi(callFor(principal));
  const [summary, daily, build, detail, migration, bags] = await Promise.all([
    api.usageSummary().catch(() => null),
    api.usageDaily({ days, client: client || undefined, line: line ?? undefined }).catch(() => null),
    api.buildBudget().catch(() => null),
    api.usageDetail({ days, client: client || undefined }).catch(() => null),
    api.getMigration().catch(() => null),
    canWrite ? null : api.listBags().catch(() => null),
  ]);
  const pending = migrationPending(migration);
  const clients = summary?.clients ?? [];
  const names = Object.fromEntries(clients.map((c) => [c.ref, c.name ?? c.ref]));
  const options = clients.map((c) => ({ ref: c.ref, name: c.name ?? c.ref }));
  const currency = summary?.currency ?? daily?.currency ?? "USD";

  return (
    <>
      <PageHeader
        eyebrow={t("nav.group.operate")}
        title={t("usage.title")}
        description={t("money.usage.description")}
        actions={
          <>
            <Button nativeButton={false} variant="outline" size="sm" render={<Link href="/usage/alerts" />}>
              {t("hu.usage.alerts.link")}
            </Button>
            {can(principal.role, "billing:manage") ? <BuyDialog /> : null}
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

      {!summary ? (
        <ErrorState title={t("money.usage.error")} />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-3" aria-label={t("money.figures")} data-slot="usage-figures">
            <Metric icon={<WalletIcon />} label={t("money.figure.available")} value={moneyText(summary.available, "down")} hint={t("money.figure.available.hint")} />
            <Metric
              icon={<Users />}
              label={t("money.figure.inBags")}
              value={`${summary.in_bags_approx ? `${t("money.approxPrefix")} ` : ""}${moneyText(summary.in_bags, "down")}`}
              hint={summary.in_bags_approx ? t("money.figure.inBags.approx") : t("money.figure.inBags.hint")}
            />
            <Metric
              icon={<CircleDollarSign />}
              label={t("money.figure.month")}
              value={moneyText(summary.month_spend)}
              hint={t("money.figure.month.hint", { amount: moneyText(summary.projected) })}
            />
          </section>

          <Section padded={false} title={t("money.table.title")} description={t("money.table.description")}>
            <UsageClientsTable clients={clients} canWrite={canWrite} days={days} />
          </Section>
        </>
      )}

      <Section id="gasto" title={t("money.chart.title")} actions={<SpendFilters days={days} client={client} line={line} clients={options} />}>
        <SpendByDay daily={daily} line={line} currency={currency} />
      </Section>

      {summary ? (
        <Section title={t("money.lines.title")} description={t("money.lines.description")} flat>
          <UsageLines lines={summary.lines} build={build} />
        </Section>
      ) : null}

      <UsageDetailPanel detail={detail} names={names} days={days} client={client} />
    </>
  );
}
