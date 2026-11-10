import { Callout, EmptyState, ErrorState, PageHeader, Section } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { CatalogGrid } from "./catalog-grid";
import { ChannelsTable } from "./channels-table";
import { ChannelsTabs } from "./channels-tabs";

export const metadata = { title: "Canales" };
export const dynamic = "force-dynamic";

/**
 * Spec 035 (R1, R3): the messaging channels Auphere offers, each with its
 * state, and every client's channels in one list. A channel is added from the
 * client's own Canales tab, where the wizard knows whose number it is.
 */
export default async function ChannelsPage() {
  const [catalog, all] = await Promise.all([
    backend.getChannelCatalog().catch(() => null),
    backend.listAllChannels().catch(() => null),
  ]);
  const active: Record<string, number> = {};
  for (const c of all?.channels ?? []) if (c.status !== "disconnected") active[c.type] = (active[c.type] ?? 0) + 1;

  return (
    <>
      <PageHeader
        title="Canales"
        description="Por dónde escriben los clientes de cada negocio. Para conectar uno, entra en el cliente y pulsa «Añadir canal»."
      />
      <ChannelsTabs current="/channels" />
      {catalog ? (
        <Section
          flat
          title="Catálogo"
          description="Lo que ya funciona, lo que está en camino («Pendiente») y lo que vendrá («Próximamente»). Solo este panel y el catálogo de canales de la consola de partners enseñan lo que todavía no se puede conectar."
        >
          <CatalogGrid catalog={catalog} active={active} />
        </Section>
      ) : null}
      <Section flat title="Canales de los clientes">
        {all === null ? (
          <ErrorState title="No se pudieron leer los canales" description="La API no respondió. Vuelve a intentarlo en un momento." />
        ) : (
          <div className="flex flex-col gap-4">
            {all.unreadable.length > 0 ? (
              <Callout tone="warning" title="Faltan clientes en la lista">
                No se pudieron leer los canales de {all.unreadable.length} cliente(s). El resto está completo.
              </Callout>
            ) : null}
            {all.channels.length === 0 ? (
              <EmptyState
                title="Todavía no hay canales"
                description="Cuando un cliente conecte su WhatsApp, aparecerá aquí."
                readonly
              />
            ) : (
              <ChannelsTable channels={all.channels} />
            )}
          </div>
        )}
      </Section>
    </>
  );
}
