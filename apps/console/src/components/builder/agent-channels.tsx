"use client";

import { MessageCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Callout, StatusBadge } from "@nexus/ui";

import { agentChannelsAction } from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { useT } from "@/i18n/client";
import type { AgentChannel, AgentChannels, ChannelPage } from "@/lib/backend/channel-config-types";

import type { Result } from "./builder-model";
import { ChannelMenu, UnlinkPending, type ChannelMenuActions } from "./channel-menu";
import { channelHref, channelStateText } from "./channel-model";
import { visibleTone } from "./life-model";
import { OwnerLinkPanel, type OwnerLinkActions } from "./owner-link-panel";

export type AgentChannelsActions = {
  reload?: (body: { ref: string; agent: string }) => Promise<Result<AgentChannels>>;
  menu?: ChannelMenuActions;
  ownerLink?: OwnerLinkActions;
};

/** Desconectado en esta visita, con lo que Meta no confirmó (34.3). */
type Unlinked = { id: string; identifier: string };

/**
 * La sección Canales de un agente (spec 047, historias 10 y 11; requisitos 29,
 * 31 y 34; parte de T115 que no depende de la 046): cada número del agente con
 * su estado visible (el mismo texto y tono en toda la consola, 25.5), el enlace
 * a su página de configuración y su ⋯ con lo que la API permite; debajo, el
 * enlace del dueño pendiente o para crearlo.
 *
 * `pages` trae, de cada número, lo que su ⋯ necesita (`allowed` y a qué agentes
 * puede pasar). Sin su página, el número se ve igual, sin ⋯.
 */
export function AgentChannelsPanel({
  refId,
  agentId,
  channels: initial,
  pages: initialPages,
  canWrite,
  fromPhone = false,
  actions = {},
}: {
  refId: string;
  agentId: string;
  /** `null` si no se pudo leer: se dice y se deja reintentar. */
  channels: AgentChannels | null;
  pages: Record<string, ChannelPage | null>;
  canWrite: boolean;
  fromPhone?: boolean;
  actions?: AgentChannelsActions;
}) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [pages, setPages] = React.useState(initialPages);
  const [unlinked, setUnlinked] = React.useState<Unlinked[]>([]);
  const reloadAction = actions.reload ?? agentChannelsAction;

  async function reload() {
    const res = await reloadAction({ ref: refId, agent: agentId });
    if (res.ok) setData(res.data);
  }

  if (!data) {
    return (
      <Callout
        tone="danger"
        action={
          <Button size="sm" variant="outline" onClick={() => void reload()}>
            {t("builder.knowledge.retry")}
          </Button>
        }
      >
        {t("builder.channels.error")}
      </Callout>
    );
  }

  function changed(page: ChannelPage) {
    setPages((prev) => ({ ...prev, [page.id]: page }));
    setData((prev) => (prev ? { ...prev, channels: prev.channels.map((c) => (c.id === page.id ? { ...c, visible_state: page.visible_state } : c)) } : prev));
  }

  function gone(channel: AgentChannel) {
    setData((prev) => (prev ? { ...prev, channels: prev.channels.filter((c) => c.id !== channel.id) } : prev));
  }

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-channels">
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("builder.channels.intro")}</p>
      {data.channels.length ? (
        <ul aria-label={t("builder.channels.list")} className="grid min-w-0 gap-3 sm:grid-cols-2">
          {data.channels.map((channel) => {
            const page = pages[channel.id] ?? null;
            return (
              <li key={channel.id} className="flex min-w-0 items-start gap-3 rounded-md border border-border p-3" data-slot="agent-channel">
                <MessageCircle aria-hidden="true" className="mt-1 size-5 shrink-0 text-muted-foreground" />
                <div className="grid min-w-0 flex-1 gap-2">
                  <Link
                    href={channelHref(refId, agentId, channel.id)}
                    aria-label={t("builder.channels.configure", { number: channel.identifier })}
                    className="min-w-0 font-medium break-words tabular-nums underline-offset-4 hover:underline"
                  >
                    {channel.identifier}
                  </Link>
                  <span className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{channel.type === "whatsapp" ? t("builder.channels.whatsapp") : channel.type}</span>
                    <StatusBadge tone={visibleTone(channel.visible_state)} data-slot="channel-state">
                      {channelStateText(t, channel.visible_state)}
                    </StatusBadge>
                  </span>
                </div>
                {page ? (
                  <ChannelMenu
                    refId={refId}
                    agentId={agentId}
                    channel={page}
                    onChanged={changed}
                    onMoved={() => gone(channel)}
                    onDisconnected={(pending) => {
                      gone(channel);
                      if (pending.length) setUnlinked((prev) => [...prev, { id: channel.id, identifier: channel.identifier }]);
                    }}
                    actions={actions.menu}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground" data-slot="agent-channels-empty">
          {t("builder.channels.empty")}
        </p>
      )}

      {unlinked.map((u) => (
        <UnlinkPending
          key={u.id}
          refId={refId}
          channelId={u.id}
          number={u.identifier}
          canWrite={canWrite}
          onDone={() => setUnlinked((prev) => prev.filter((x) => x.id !== u.id))}
          disconnect={actions.menu?.disconnect}
        />
      ))}

      <OwnerLinkPanel
        refId={refId}
        agentId={agentId}
        pending={data.pending_link}
        canWrite={canWrite}
        fromPhone={fromPhone}
        actions={actions.ownerLink}
      />
    </div>
  );
}
