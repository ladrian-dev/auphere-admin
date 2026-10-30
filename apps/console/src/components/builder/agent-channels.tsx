"use client";

import { MessageCircle, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, StatusBadge } from "@nexus/ui";

import { agentChannelsAction } from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { BrandLogo, hasBrandLogo } from "@/components/brand-logo";
import { useMetaSocialConnect } from "@/components/channels/meta-social-connect";
import type { MetaSignupConfig } from "@/components/channels/whatsapp-connect";
import { useT } from "@/i18n/client";
import type { AgentChannel, AgentChannels, ChannelPage } from "@/lib/backend/channel-config-types";
import type { MetaSocialConnectResult, WhatsAppSignupResult } from "@/lib/backend/channels";

import type { Result } from "./builder-model";
import { ChannelMenu, UnlinkPending, type ChannelMenuActions } from "./channel-menu";
import { channelHref, channelStateText, channelSummary } from "./channel-model";
import { ChannelWizard, type ChannelKind, type WizardStep } from "./channel-picker";
import { CONNECT_ACTIONS, ConnectWhatsApp, type ConnectActions, type ConnectStage, type Placed } from "./connect-whatsapp-dialog";
import { visibleTone } from "./life-model";
import { OwnerLinkPanel, type OwnerLinkActions } from "./owner-link-panel";

export type AgentChannelsActions = {
  reload?: (body: { ref: string; agent: string }) => Promise<Result<AgentChannels>>;
  menu?: ChannelMenuActions;
  ownerLink?: OwnerLinkActions;
  connect?: ConnectActions;
};

/** Desconectado en esta visita, con lo que Meta no confirmó (34.3). */
type Unlinked = { id: string; identifier: string };

/**
 * La pestaña Canales de un agente (spec 047, historias 10 y 11; requisitos
 * 29, 31 y 34), como el prototipo aprobado (`agente.md` §7 y hueco H4):
 *
 * - Sin números: el asistente de cuatro pasos con la rejilla de canales
 *   (`ChannelWizard`). WhatsApp abre «Conectar WhatsApp» (`ConnectWhatsApp`),
 *   que usa el alta de Meta de la consola y deja el número en este agente.
 * - Con números: una tarjeta con una fila por número (logo, a quién responde
 *   y a quién escala, su estado visible —el mismo texto y tono en toda la
 *   consola, 25.5— y su ⋯ con lo que la API permite) y «Añadir otro canal»,
 *   que despliega el mismo asistente debajo.
 * - Con un enlace del dueño pendiente: su tarjeta arriba, y WhatsApp no abre
 *   otra conexión hasta revocarlo.
 *
 * `pages` trae, de cada número, lo que su ⋯ y su línea necesitan. Sin su
 * página, el número se ve igual, sin ⋯. Quien solo lee no ve el asistente.
 */
export function AgentChannelsPanel({
  refId,
  agentId,
  channels: initial,
  pages: initialPages,
  canWrite,
  fromPhone = false,
  clientName = null,
  meta = null,
  updated = null,
  actions = {},
}: {
  refId: string;
  agentId: string;
  /** `null` si no se pudo leer: se dice y se deja reintentar. */
  channels: AgentChannels | null;
  pages: Record<string, ChannelPage | null>;
  canWrite: boolean;
  fromPhone?: boolean;
  /** «Elige cómo se conecta el número de {cliente}». */
  clientName?: string | null;
  /** La configuración del alta de Meta de este entorno (nunca el secreto). Sin ella, se dice quién conecta el número. */
  meta?: MetaSignupConfig | null;
  /** Spec 047 (63.1): lo último que guardó la configuración de un canal, abierta dentro del agente. */
  updated?: ChannelPage | null;
  actions?: AgentChannelsActions;
}) {
  const t = useT();
  const router = useRouter();
  const [data, setData] = React.useState(initial);
  const [pages, setPages] = React.useState(initialPages);
  const [unlinked, setUnlinked] = React.useState<Unlinked[]>([]);
  const [stage, setStage] = React.useState<ConnectStage | null>(null);
  const [connecting, setConnecting] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const wizardTitle = React.useRef<HTMLHeadingElement>(null);
  const listTitle = React.useId();
  const reloadAction = actions.reload ?? agentChannelsAction;
  const connect = actions.connect ?? CONNECT_ACTIONS;

  // La configuración del canal guardó: su fila dice lo nuevo (estado, a quién responde, a quién escala).
  const [seen, setSeen] = React.useState(updated);
  if (updated && updated !== seen) {
    setSeen(updated);
    setPages((prev) => ({ ...prev, [updated.id]: updated }));
    setData((prev) => (prev ? { ...prev, channels: prev.channels.map((c) => (c.id === updated.id ? { ...c, visible_state: updated.visible_state } : c)) } : prev));
  }

  // «Añadir otro canal» desaparece al pulsarlo: el foco pasa al asistente.
  React.useEffect(() => {
    if (adding) wizardTitle.current?.focus();
  }, [adding]);

  async function reload() {
    const res = await reloadAction({ ref: refId, agent: agentId });
    if (res.ok) setData(res.data);
    return res;
  }

  /** Spec 049: the connected Instagram account or Page goes to this agent,
   *  the same way a number connected from here does (34.2). */
  async function placeSocial(res: MetaSocialConnectResult) {
    const id = res.channel?.id;
    if (!id) return;
    const reloaded = await reload();
    if (!(reloaded.ok && reloaded.data.channels.some((c) => c.id === id))) {
      const moved = await connect.move({ ref: refId, channel: id, to: agentId });
      if (moved.ok) await reload();
    }
    // Like a WhatsApp number: straight to its page to say who it answers
    // (QA 2026-10-30: it stayed on the picker saying «the agent answers»).
    router.push(channelHref(refId, agentId, id));
  }

  const social = useMetaSocialConnect({ refId, offer: data?.meta_social ?? null, onConnected: placeSocial });
  const socialKinds = (data?.meta_social?.channels ?? []).map((c) => c.kind);

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

  /**
   * El alta de la consola deja el número en el cliente (lo atiende el agente
   * principal). Si este no lo es, se le pasa (34.2). Un agente sin guardar no
   * puede recibirlo: el número queda en el principal y se dice.
   */
  async function place(result: WhatsAppSignupResult): Promise<Placed> {
    const res = await reload();
    if (res.ok && res.data.channels.some((c) => c.id === result.channel_id)) return "here";
    const moved = await connect.move({ ref: refId, channel: result.channel_id, to: agentId });
    if (!moved.ok) return "elsewhere";
    const page = moved.data;
    setPages((prev) => ({ ...prev, [page.id]: page }));
    setData((prev) =>
      prev && !prev.channels.some((c) => c.id === page.id)
        ? { ...prev, channels: [...prev.channels, { id: page.id, type: page.type, identifier: page.identifier, visible_state: page.visible_state }] }
        : prev,
    );
    return "here";
  }

  function pick(kind: ChannelKind["id"]) {
    if ((kind === "instagram" || kind === "messenger") && socialKinds.includes(kind)) {
      void social.start(kind);
      return;
    }
    if (kind !== "whatsapp") return;
    if (data?.pending_link) {
      toast.warning(t("channels.proto.linkPending"));
      return;
    }
    setStage("method");
  }

  const list = data.channels;
  // The wizard only shows while choosing a channel (none yet, or «Añadir otro
  // canal»): choosing, or Meta's window open. «Configurar» happens on the
  // channel's page, which says «Paso 3 de 4» itself (QA 2026-10-30: it showed
  // «¡Listo!» while the person was still choosing).
  const step: WizardStep = stage !== null || connecting || social.working ? 1 : 0;
  const count = (kind: string) => list.filter((c) => c.type === kind).length;
  const wizard = canWrite ? (
    <ChannelWizard
      step={step}
      connected={{ whatsapp: count("whatsapp"), instagram: count("instagram"), messenger: count("messenger") }}
      onConnect={pick}
      headingRef={wizardTitle}
      available={socialKinds}
    />
  ) : null;

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-channels">
      {data.pending_link ? (
        <OwnerLinkPanel
          refId={refId}
          agentId={agentId}
          pending={data.pending_link}
          canWrite={canWrite}
          fromPhone={fromPhone}
          actions={actions.ownerLink}
          onCreated={(pending) => setData((prev) => (prev ? { ...prev, pending_link: pending } : prev))}
          onRevoked={() => setData((prev) => (prev ? { ...prev, pending_link: null } : prev))}
        />
      ) : null}

      {list.length ? (
        <section aria-labelledby={listTitle} className="grid min-w-0 gap-4">
          <h2 id={listTitle} className="sr-only">
            {t("builder.screen.channels")}
          </h2>
          <ul aria-label={t("builder.channels.list")} className="grid min-w-0 divide-y divide-border rounded-lg border border-border bg-card">
            {list.map((channel) => {
              const page = pages[channel.id] ?? null;
              return (
                <li key={channel.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3" data-slot="agent-channel">
                  {hasBrandLogo(channel.type) ? (
                    <BrandLogo brand={channel.type} size="md" />
                  ) : (
                    <MessageCircle aria-hidden="true" className="size-8 shrink-0 text-muted-foreground" />
                  )}
                  <div className="grid min-w-0 flex-1 basis-48 gap-1">
                    <Link
                      href={channelHref(refId, agentId, channel.id)}
                      aria-label={t("builder.channels.configure", { number: channel.identifier })}
                      className="min-w-0 font-medium break-words tabular-nums underline-offset-4 hover:underline"
                    >
                      {channel.identifier}
                    </Link>
                    <span className="text-xs text-pretty text-muted-foreground">{channelSummary(t, channel.type, page)}</span>
                  </div>
                  <StatusBadge tone={visibleTone(channel.visible_state)} data-slot="channel-state">
                    {channelStateText(t, channel.visible_state)}
                  </StatusBadge>
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
          {canWrite && !adding ? (
            <Button variant="outline" className="justify-self-start" onClick={() => setAdding(true)}>
              <Plus aria-hidden="true" />
              {t("channels.proto.add")}
            </Button>
          ) : null}
        </section>
      ) : null}

      {list.length === 0
        ? (wizard ?? (
            <p className="text-sm text-muted-foreground" data-slot="agent-channels-empty">
              {t("builder.channels.empty")}
            </p>
          ))
        : adding
          ? wizard
          : null}

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

      {canWrite ? social.dialog : null}

      {canWrite ? (
        <ConnectWhatsApp
          refId={refId}
          agentId={agentId}
          clientName={clientName}
          meta={meta}
          fromPhone={fromPhone}
          stage={stage}
          onStage={setStage}
          onVeil={setConnecting}
          onConnected={place}
          onLinkCreated={(pending) => setData((prev) => (prev ? { ...prev, pending_link: pending } : prev))}
          ownerLinkActions={actions.ownerLink}
          actions={connect}
        />
      ) : null}
    </div>
  );
}
