import { ErrorState, PageHeader } from "@nexus/ui";

import { isChannelOnly } from "@/components/connectors/labels";
import { backend } from "@/lib/backend";

import { ConnectorsCatalog } from "./connectors-catalog";

export const metadata = { title: "Conectores" };
export const dynamic = "force-dynamic";

const LIVE = new Set(["connected", "partial", "needs_reauth", "pending", "paused", "error"]);

/**
 * Spec 035 (R4): the apps the agents can work with, like Chatwoot's
 * Integrations — searchable, grouped, with how many clients use each.
 * WhatsApp and TikTok are channels and live in Canales.
 */
export default async function ConnectorsCatalogPage() {
  const [connectors, installs] = await Promise.all([
    backend.listConnectors().catch(() => null),
    backend.listConnectorInstalls().catch(() => ({}) as Record<string, never>),
  ]);
  return (
    <>
      <PageHeader
        title="Conectores"
        description="Las apps con las que trabajan los agentes: citas, cobros, tienda, documentos. Cada cliente las conecta desde su ficha, en Conectores."
      />
      {connectors === null ? (
        <ErrorState title="No se pudo leer el catálogo" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <ConnectorsCatalog
          rows={connectors
            .filter((c) => !isChannelOnly(c) && c.status !== "deprecated")
            .map((c) => ({
              connector: c,
              installs: (installs[c.slug] ?? []).filter((i) => LIVE.has(i.status)).length,
            }))}
        />
      )}
    </>
  );
}
