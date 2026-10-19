import { Callout, EmptyState, ErrorState, PageHeader, Section } from "@nexus/ui";

import { ChannelIcon } from "@/components/brand/channel-icon";
import { AVAILABILITY_LABEL } from "@/components/channels/labels";
import { backend } from "@/lib/backend";

import { ChannelsTable } from "./channels-table";

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
  const countOf = (key: string) => all?.channels.filter((c) => c.type === key && c.status !== "disconnected").length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Plataforma"
        title="Canales"
        description="Por dónde escriben los clientes de cada negocio. Para conectar uno, entra en el cliente y pulsa «Añadir canal»."
      />
      {catalog ? (
        <Section flat title="Catálogo" description="Lo que ya funciona, lo que está en camino y lo que vendrá.">
          <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {catalog.map((entry) => {
              const badge = AVAILABILITY_LABEL[entry.availability];
              return (
                <li
                  key={entry.key}
                  className="flex flex-col items-start gap-2 rounded-md p-4 ring-1 ring-foreground/10"
                  aria-disabled={entry.availability === "coming_soon" || undefined}
                >
                  <ChannelIcon
                    channel={entry.key}
                    className={entry.availability === "coming_soon" ? "size-6 opacity-50" : "size-6"}
                  />
                  <span className="text-sm font-medium">{entry.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {badge ?? `${countOf(entry.key)} activos`}
                  </span>
                </li>
              );
            })}
          </ul>
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
