import Link from "next/link";

import { Callout, PageHeader, cn } from "@nexus/ui";
import { ReadError } from "@/components/states/read-error";
import { modelsBackend, type SalePolicy } from "@/lib/backend-models";
import { ROUTER_PANEL_VISIBLE } from "@/lib/router-panel";

import { MultiplierDialog, NewDeploymentDialog } from "./deployment-dialogs";
import { DeploymentsTable } from "./deployments-table";
import { STATUS_FILTERS, formatMultiplier, problemWords } from "./labels";

export const metadata = { title: "Modelos" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T150, historia 24) and spec 059 (historias 1, 3 y 4): the catalog
 * of models without touching the database — what each one costs Auphere and
 * what the partner pays for it, the target multiplier of the platform, and
 * the operator's writes. A model in use offers neither «Retirar» nor «No
 * disponible»; the API refuses them anyway. With the router parked
 * (`lib/router-panel.ts`) there is no «Nuevo despliegue».
 */
export default async function ModelsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const status = (await searchParams).status;
  const valid = STATUS_FILTERS.some((f) => f.key === status) ? status : undefined;
  const data = await modelsBackend
    .listDeployments(valid && valid !== "all" ? { status: valid } : {})
    .catch(() => null);
  const policy = data?.sale_policy ?? null;
  const unpriced = data?.items.filter((r) => r.current_price === null && r.deployment.status === "active") ?? [];
  const unverified = data?.items.find((r) => !r.uses.verified) ?? null;

  return (
    <>
      <PageHeader
        title="Modelos"
        description="Lo que cuesta cada modelo a Auphere y lo que paga el partner por él, en US$ por millón de tokens."
        actions={
          policy || ROUTER_PANEL_VISIBLE ? (
            <>
              {policy ? <TargetMultiplier policy={policy} /> : null}
              {ROUTER_PANEL_VISIBLE ? <NewDeploymentDialog /> : null}
            </>
          ) : null
        }
      />
      <nav aria-label="Estado" className="flex flex-wrap gap-1 rounded-md bg-muted p-1 text-sm sm:w-fit">
        {STATUS_FILTERS.map((f) => {
          const current = (valid ?? "all") === f.key;
          return (
            <Link
              key={f.key}
              href={f.key === "all" ? "/models" : `/models?status=${f.key}`}
              aria-current={current ? "page" : undefined}
              className={cn(
                "rounded-sm px-3 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                current ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </Link>
          );
        })}
      </nav>
      {data === null ? (
        <ReadError title="No se pudo leer el catálogo" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <>
          {data.sale_policy.multiplier === null ? (
            <Callout tone="warning" title="Sin multiplicador objetivo">
              No se pudo leer el multiplicador objetivo: los modelos se ven, pero no se pueden proponer pesos de venta
              ni marcar los desfasados.
            </Callout>
          ) : null}
          {unverified ? (
            <Callout tone="warning" title="No se puede comprobar qué modelos usa la plataforma">
              {sentence(problemWords(unverified.uses.problem))}. Mientras tanto, la API rechaza «Retirar» y «No
              disponible» sobre cualquier modelo.
            </Callout>
          ) : null}
          {unpriced.length ? (
            <Callout tone="warning" title="Activos sin coste">
              {unpriced.length === 1 ? "Un modelo activo no tiene" : `${unpriced.length} modelos activos no tienen`} un
              coste en vigor: no se puede calcular su margen ni proponer sus pesos de venta.
            </Callout>
          ) : null}
          <DeploymentsTable rows={data.items} policy={data.sale_policy} routerVisible={ROUTER_PANEL_VISIBLE} />
        </>
      )}
    </>
  );
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** The target multiplier of the platform, its floor and «Cambiar» (3.6, 3.7). */
function TargetMultiplier({ policy }: { policy: SalePolicy }) {
  return (
    <div
      role="group"
      aria-label="Multiplicador objetivo"
      className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border px-3 py-1"
    >
      <span className="text-xs text-muted-foreground">Multiplicador objetivo</span>
      <span className="font-mono text-sm font-medium tabular-nums">
        {policy.multiplier === null ? "Sin leer" : formatMultiplier(policy.multiplier)}
      </span>
      <span className="text-xs text-muted-foreground">suelo {formatMultiplier(policy.floor)}</span>
      <MultiplierDialog policy={policy} />
    </div>
  );
}
