import Link from "next/link";

import { Callout, ErrorState, Metric, PageHeader, Section, cn } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { formatCents } from "@/lib/format";

import { PERIODS, formatPct, formatUsd, parsePeriod, periodQuery } from "./period";
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
        description="Lo que gastan todos los partners y sus clientes, lo que le cuesta a Auphere y lo que gana."
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
          {/* Spec 039: what Auphere earns on consumption, in money and in %. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Venta"
              value={formatCents(data.totals.spend_cents)}
              hint="Lo que se descontó del saldo de los partners"
            />
            <Metric
              label="Coste del modelo"
              value={formatUsd(data.totals.cost_usd)}
              hint="Lo que costaron esos mismos turnos"
            />
            <Metric
              label="Ganancia"
              value={formatUsd(data.totals.profit_usd)}
              hint={`Margen ${formatPct(data.totals.margin_pct)} de cada dólar vendido`}
            />
            <Metric
              label="Se cobra sobre el coste"
              value={formatPct(data.totals.markup_pct)}
              hint={
                data.totals.effective_multiplier !== null
                  ? `Coste × ${data.totals.effective_multiplier.toLocaleString("es")} · tarifa fijada × ${Number(data.totals.configured_multiplier).toLocaleString("es")}`
                  : `Tarifa fijada: coste × ${Number(data.totals.configured_multiplier).toLocaleString("es")}`
              }
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric
              label="Ganancia neta"
              value={formatUsd(data.totals.net_profit_usd)}
              hint={`Después de ${formatUsd(data.totals.tests_cost_usd)} de pruebas en el Playground`}
            />
            <Metric
              label="Mensajes"
              value={data.totals.messages.toLocaleString("es")}
              hint={`${data.totals.conversations.toLocaleString("es")} conversaciones · ${data.totals.active_clients} clientes activos`}
            />
            <Metric
              label="Eventos sin precio"
              value={data.totals.unpriced_events.toLocaleString("es")}
              hint={
                data.totals.unpriced_events > 0
                  ? "Su coste no se conoce: la ganancia real es menor"
                  : "Todo lo vendido tiene su coste"
              }
            />
          </div>
          <Section title="Venta, coste y ganancia por día" description="Todos los partners juntos.">
            <SpendChart daily={data.daily} />
          </Section>
          <UsageTables data={data} />
          <p className="text-xs text-pretty text-muted-foreground">
            La venta sale del libro de cada partner y el coste, de lo que el modelo cobró por esos mismos turnos. Las
            pruebas del Playground las paga Auphere y no se cobran a nadie: van aparte y solo restan de la ganancia neta.
            Los clientes directos de Auphere no tienen saldo de partner, así que su venta es «Sin saldo» y su ganancia,
            negativa.
          </p>
        </>
      )}
    </>
  );
}
