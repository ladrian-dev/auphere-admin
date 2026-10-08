"use client";

import Link from "next/link";
import * as React from "react";

import { CatalogBrowser } from "@nexus/ui";

import { useCatalog, useCatalogLabels } from "@/components/catalog/use-catalog";
import { useT } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";
import type { ChannelDetail } from "@/lib/backend/channels";

import { ChannelCard } from "./channel-card";

/**
 * Canales (spec 018, R4): por dónde llegan los mensajes, con **el mismo
 * patrón de navegación** que Habilidades y Conectores.
 *
 * **Lo que no se puede conectar no está en la lista** (constitución §V, y
 * R4.7). Messenger, Instagram y Telegram no aparecen apagados ni
 * «próximamente»: el filtro lo hace `f2VisibleChannels` antes de llegar
 * aquí, y por eso esta lista es corta a propósito.
 *
 * Hoy es corta de verdad —un canal—, y aun así usa el patrón: es lo que
 * hace que quien aprendió a moverse por Habilidades no tenga que aprender
 * nada al llegar. Las pastillas de categoría, que no filtrarían nada, no se
 * pintan: eso lo decide el patrón, no esta pantalla.
 */
export function ChannelsList({
  refId,
  channels,
  manage,
  empty,
  agents = [],
  agentOf = {},
}: {
  refId: string;
  channels: ChannelDetail[];
  manage: boolean;
  /** Spec 030: the client's agents (empty with one) and who answers on each number. */
  agents?: ClientAgent[];
  agentOf?: Record<string, string>;
  /** El cartel de «no hay ninguno», que trae su propia salida desde el
   *  servidor: solo la página sabe si hoy se puede conectar. */
  empty: React.ReactNode;
}) {
  const t = useT();
  const catalog = useCatalog(`/clients/${encodeURIComponent(refId)}/channels`);
  const labels = useCatalogLabels({ title: t("ch.title") });
  const showRoles = channels.filter((c) => c.status === "active").length > 1;

  const items = React.useMemo(
    () =>
      channels.map((c) => ({
        id: c.id,
        name: c.verified_name ?? c.provider_identifier,
        search: `${c.type} ${c.provider} ${c.provider_identifier}`,
        // Un solo tipo de canal hoy: sin categorías que separar, el patrón
        // no pinta pastillas. Inventarle una sería una categoría de una.
        category: null,
        active: c.status === "active",
        channel: c,
      })),
    [channels],
  );

  return (
    <CatalogBrowser
      {...catalog}
      items={items}
      labels={labels}
      renderLink={(href, children, props) => (
        <Link href={href} {...props}>
          {children}
        </Link>
      )}
      renderItem={({ id, channel }) => (
        <ChannelCard key={id} refId={refId} channel={channel} manage={manage} showRoles={showRoles} agents={agents} agentId={agentOf[channel.id]} />
      )}
      empty={empty}
    />
  );
}
