import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { IntegrationsList } from "@/components/integrations/integrations-list";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { ConnectorOut } from "@/lib/backend/agent-tools";
import { can, requirePartnerPrincipal } from "@/lib/principal";

/**
 * Integraciones (spec 017, R4): su propia pantalla.
 *
 * Hasta ahora las cabeceras de conector vivían dentro de Herramientas, entre
 * las casillas de la lista blanca, y la URL `/integrations` solo redirigía
 * allí. Eran dos cosas distintas compartiendo sitio: elegir qué sabe hacer el
 * agente y conectarlo con lo que el negocio ya usa.
 *
 * Que los conectores no carguen **no tumba la pantalla**: se dice en una
 * alerta y lo demás sigue. Aquí es casi todo, así que es sobre todo una
 * promesa de no mentir con una pantalla en blanco.
 */
export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("int.title") };
}

export default async function IntegrationsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/integrations`);
  if (!can(principal.role, "agents:read")) redirect(`/clients/${encodeURIComponent(ref)}`);
  const { t } = await getT(principal.locale);

  const { connectors, error } = await backendFor(principal)
    .listConnectors(ref)
    .then(
      (c) => ({ connectors: c, error: null as string | null }),
      (err: unknown) => {
        if (err instanceof BackendError) return { connectors: [] as ConnectorOut[], error: err.detail };
        throw err;
      },
    );

  return (
    <section aria-label={t("int.title")} className="flex flex-col gap-(--space-section)">
      <PageHeader title={t("int.title")} description={t("int.description")} />
      <IntegrationsList
        refId={ref}
        connectors={connectors}
        error={error}
        canWrite={can(principal.role, "agents:write")}
      />
    </section>
  );
}
