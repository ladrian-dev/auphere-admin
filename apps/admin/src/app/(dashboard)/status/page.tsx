import Link from "next/link";

import { DescriptionList, ErrorState, PageHeader, Section, StatusBadge } from "@nexus/ui";

import { SectionTabs } from "@/components/shell/section-tabs";
import { backend } from "@/lib/backend";
import { leversBackend } from "@/lib/backend-levers";
import { modelsBackend } from "@/lib/backend-models";

import { AnomaliesView } from "../router/anomalies/anomalies-view";
import { DAY_OPTIONS, anomalyTotals, daysLabel, parseDays, sinceFor } from "./anomalies";
import { LedgerDiffs, MetaDiffs } from "./reconciliations-view";

export const metadata = { title: "Estado" };
export const dynamic = "force-dynamic";

const ENV_LABEL: Record<string, string> = { production: "Producción", staging: "Staging", dev: "Desarrollo local" };
const CHECK_LABEL: Record<string, string> = { postgres: "Base de datos", redis: "Redis" };

const n = (value: number | null) => (value === null ? "Sin leer" : value);

/**
 * Spec 031 (R6): is the API up, where is it, and what is deployed. Spec 047
 * (T172; 54.9, 43.9, 2.6): and what Auphere has to look at — the router's
 * reserve models and «Sin modelo disponible», the ledger's differences and
 * Meta's reconciliation of messages.
 */
export default async function StatusPage({ searchParams }: { searchParams: Promise<{ days?: string | string[] }> }) {
  const days = parseDays((await searchParams).days);
  const [instance, router, recon] = await Promise.all([
    backend.getInstance().catch(() => null),
    modelsBackend.anomalies(sinceFor(days)).catch(() => null),
    leversBackend.reconciliations(days).catch(() => null),
  ]);
  const totals = anomalyTotals(router, recon);
  return (
    <>
      <PageHeader title="Estado" description="Qué entorno es este, qué versión corre, si sus dependencias responden y qué anomalías hay que mirar." />
      {!instance ? (
        <ErrorState title="La API no responde" description="No se pudo leer el estado de la instancia. Si persiste, revisa el despliegue de la API." />
      ) : (
        <>
          <Section title="Despliegue">
            <DescriptionList
              items={[
                { key: "env", term: "Entorno", detail: ENV_LABEL[instance.environment] ?? instance.environment },
                { key: "schema", term: "Versión del esquema", detail: instance.schema_revision ?? "No se pudo leer", mono: true },
                { key: "commit", term: "Commit de la API", detail: instance.commit === "unknown" ? "Sin dato (build local)" : instance.commit.slice(0, 12), mono: true },
              ]}
            />
          </Section>
          <Section title="Dependencias">
            <ul className="flex flex-col divide-y divide-border">
              {Object.entries(instance.checks).map(([name, value]) => (
                <li key={name} className="flex items-center justify-between gap-4 py-3">
                  <span className="text-sm">{CHECK_LABEL[name] ?? name}</span>
                  {value === "ok" ? (
                    <StatusBadge tone="positive">Responde</StatusBadge>
                  ) : (
                    <StatusBadge tone="danger">{value.replace("error: ", "Error · ")}</StatusBadge>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        </>
      )}

      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Anomalías</h2>
        <SectionTabs
          label="Periodo de las anomalías"
          tabs={DAY_OPTIONS.map((d) => ({ href: `/status?days=${d}`, label: daysLabel(d) }))}
          current={`/status?days=${days}`}
        />
        <Section flat>
          <DescriptionList
            layout="stacked"
            columns={3}
            items={[
              { key: "reserve", term: "Con modelo de reserva", detail: n(totals.reserve) },
              { key: "no_model", term: "Sin modelo", detail: n(totals.noModel) },
              { key: "waiting", term: "Esperan por «Sin modelo disponible»", detail: n(totals.waiting) },
              { key: "ledger", term: "Diferencias del libro", detail: n(totals.ledger) },
              { key: "meta", term: "Días con diferencias con Meta", detail: n(totals.meta) },
            ]}
          />
        </Section>
        <Section
          title="Router"
          description="Las decisiones que cayeron en el modelo de reserva o se quedaron sin modelo en la residencia del cliente, y quién espera en la Bandeja por «Sin modelo disponible»."
          actions={
            <Link href="/router/anomalies" className="text-sm text-primary-deep underline-offset-4 hover:underline">
              Abrir en Router
            </Link>
          }
        >
          {router === null ? (
            <ErrorState title="No se pudieron leer las anomalías del router" description="La API no respondió. Vuelve a intentarlo en un momento." />
          ) : (
            <AnomaliesView data={router} />
          )}
        </Section>
        <Section title="Libro de las bolsas" description="El cuadre de cada bolsa y de cada cuenta, calculado ahora: lo mismo que el proceso diario.">
          {recon === null ? (
            <ErrorState title="No se pudieron leer las conciliaciones" description="La API no respondió. Vuelve a intentarlo en un momento." />
          ) : (
            <LedgerDiffs rows={recon.ledger} />
          )}
        </Section>
        <Section
          title="Mensajes de Meta"
          description="Cada día se comparan los mensajes que Meta entregó a cada número con los guardados. Aquí, los días que no coinciden."
        >
          {recon === null ? (
            <ErrorState title="No se pudieron leer las conciliaciones" description="La API no respondió. Vuelve a intentarlo en un momento." />
          ) : (
            <MetaDiffs rows={recon.meta} />
          )}
        </Section>
      </div>
    </>
  );
}
