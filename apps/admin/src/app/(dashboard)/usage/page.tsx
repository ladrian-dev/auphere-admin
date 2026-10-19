import Link from "next/link";

import { Callout, ErrorState, Metric, PageHeader, Section, cn } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { formatCents } from "@/lib/format";

import { PERIODS, formatUsd, parsePeriod, periodQuery } from "./period";
import { SpendChart } from "./spend-chart";
import { UsageTables } from "./usage-tables";

export const metadata = { title: "Consumo" };
export const dynamic = "force-dynamic";

/**
 * Spec 038: what every partner and every client consumed — the operator's
 * money view of the whole platform. What the clients paid (sale price, from
 * each partner's book) and what it cost Auphere (the model) are two figures,
 * never one (spec 033 R7.2).
 */
export default async function UsagePage({ searchParams }: { searchParams: Promise<{ period?: string }> }) {
  const period = parsePeriod((await searchParams).period);
  const data = await backend.getUsageOverview(periodQuery(period)).catch(() => null);

  return (
    <>
      <PageHeader
        title="Consumo"
        description="Lo que gastan todos los partners y sus clientes, y lo que le cuesta a Auphere."
        actions={
          <nav aria-label="Periodo" className="flex rounded-md bg-muted p-1 text-sm">
            {PERIODS.map((p) => (
              <Link
                key={p.key}
                href={p.key === "month" ? "/usage" : `/usage?period=${p.key}`}
                aria-current={p.key === period ? "page" : undefined}
                className={cn(
                  "rounded-sm px-3 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  p.key === period ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {p.label}
              </Link>
            ))}
          </nav>
        }
      />
      {data === null ? (
        <ErrorState title="No se pudo leer el consumo" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <>
          {data.unreadable.partners.length + data.unreadable.clients.length > 0 ? (
            <Callout tone="warning" title="Faltan datos">
              No se pudieron leer {data.unreadable.partners.length} partner(s) y {data.unreadable.clients.length}{" "}
              cliente(s). Las cifras de arriba no los incluyen.
            </Callout>
          ) : null}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Gasto de los clientes"
              value={formatCents(data.totals.spend_cents)}
              hint="A precio de venta, del saldo recargado"
            />
            <Metric label="Coste interno" value={formatUsd(data.totals.internal_cost_usd)} hint="Lo que costó el modelo a Auphere" />
            <Metric label="Margen" value={formatUsd(data.totals.margin_usd)} hint="Gasto menos coste interno" />
            <Metric
              label="Mensajes"
              value={data.totals.messages.toLocaleString("es")}
              hint={`${data.totals.conversations.toLocaleString("es")} conversaciones · ${data.totals.active_clients} clientes activos`}
            />
          </div>
          <Section title="Gasto por día" description="Todos los partners juntos, a precio de venta.">
            <SpendChart daily={data.daily} />
          </Section>
          <UsageTables data={data} />
          <p className="text-xs text-pretty text-muted-foreground">
            Los clientes directos de Auphere no tienen saldo de partner: su gasto sale como «Sin saldo» y solo cuenta su
            coste interno. El coste interno incluye las pruebas del Playground, que también se pagan.
          </p>
        </>
      )}
    </>
  );
}
