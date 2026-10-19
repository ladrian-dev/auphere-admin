import { ErrorState, PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { CapabilitiesCatalog } from "./catalog";

export const dynamic = "force-dynamic";

/**
 * Spec 037: Habilidades — what the agent knows how to do, the same screen as
 * the partner console's client page. Each change goes to the draft;
 * publishing stays a separate step in Agente.
 */
export default async function CapabilitiesPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ all?: string; agent?: string }>;
}) {
  const { id } = await params;
  const { all, agent } = await searchParams;
  const data = await backend.getCapabilities(id, { all: all === "1", agent }).catch(() => null);
  const base = `/tenants/${id}/capabilities`;
  const own = agent ? `${base}?agent=${encodeURIComponent(agent)}` : base;

  return (
    <section aria-label="Habilidades" className="flex flex-col gap-6">
      <PageHeader
        size="compact"
        title="Habilidades"
        description="Lo que el agente sabe hacer. Lo que dejes apagado, el agente no lo ve. Cada cambio se guarda en el borrador, y publicar sigue siendo un paso aparte."
      />
      {data === null ? (
        <ErrorState title="No se pudieron leer las habilidades" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <CapabilitiesCatalog
          tenantId={id}
          data={data}
          seeAllHref={`${own}${agent ? "&" : "?"}all=1`}
          seeOwnHref={own}
          agentId={agent}
        />
      )}
    </section>
  );
}
