import Link from "next/link";

import { Callout, ErrorState, PageHeader, cn } from "@nexus/ui";
import { modelsBackend } from "@/lib/backend-models";

import { NewDeploymentDialog } from "./deployment-dialogs";
import { DeploymentsTable } from "./deployments-table";
import { STATUS_FILTERS } from "./labels";

export const metadata = { title: "Modelos" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T150, historia 24): the catalog of deployments — a model in a
 * provider and a route — without touching the database. Dar de alta (in
 * draft), poner precio con vigencia, activar por la puerta, retirar con fecha y
 * marcar «No disponible». The router reads every change from the next turn.
 */
export default async function ModelsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const status = (await searchParams).status;
  const valid = STATUS_FILTERS.some((f) => f.key === status) ? status : undefined;
  const data = await modelsBackend
    .listDeployments(valid && valid !== "all" ? { status: valid } : {})
    .catch(() => null);
  const unpriced = data?.items.filter((r) => r.current_price === null && r.deployment.status === "active") ?? [];

  return (
    <>
      <PageHeader
        title="Modelos"
        description="Cada despliegue es un modelo en un proveedor y una ruta. Ninguno se usa sin contrato sin retención, alta de subprocesador, licencia leída, pesos del medidor y certificación."
        actions={<NewDeploymentDialog />}
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
        <ErrorState
          title="No se pudo leer el catálogo"
          description="La API no respondió. Vuelve a intentarlo en un momento."
        />
      ) : (
        <>
          {unpriced.length ? (
            <Callout tone="warning" title="Activos sin precio">
              {unpriced.length} despliegue(s) activos no tienen un precio en vigor: el router no los elige
              hasta que lo tengan.
            </Callout>
          ) : null}
          <DeploymentsTable rows={data.items} />
        </>
      )}
    </>
  );
}
