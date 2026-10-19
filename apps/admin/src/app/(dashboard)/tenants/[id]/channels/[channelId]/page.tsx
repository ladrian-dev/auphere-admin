import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button, Callout, DescriptionList, EmptyState, StatusDot } from "@nexus/ui";

import { ChannelIcon } from "@/components/brand/channel-icon";
import { CHANNEL_NAME, CHANNEL_STATUS, ROLE_LABEL } from "@/components/channels/labels";
import { backend, type ChannelOut } from "@/lib/backend";
import { channelAgentEnabled, channelRole } from "@/lib/channels";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  DisconnectButton,
  PauseConnectorButton,
  ResumeConnectorButton,
} from "../../_integrations/connector-actions";
import { MetaConnectOwnedDialog } from "../../_integrations/meta-connect-owned-dialog";
import { MetaWhatsAppSetupDialog } from "../../_integrations/meta-signup-dialog";
import { MetaTestSendDialog } from "../../_integrations/meta-test-send-dialog";
import { TikTokConnectDialog } from "../../_integrations/tiktok-connect-dialog";
import { WhatsAppTemplatesDialog } from "../../_integrations/whatsapp-templates-dialog";
import { ChannelAgentForm } from "./channel-agent-form";
import { ChannelSettings } from "./channel-settings";

export const dynamic = "force-dynamic";

/** The connector row that carries each channel's credentials. */
const CONNECTOR_OF: Record<string, string> = { whatsapp: "whatsapp_meta", tiktok: "tiktok_bm" };

type Tab = "settings" | "agent" | "templates" | "health";

function displayName(c: ChannelOut): string {
  const cfg = c.config ?? {};
  for (const key of ["verified_name", "display_name", "display_phone_number"]) {
    const v = cfg[key];
    if (typeof v === "string" && v) return v;
  }
  return CHANNEL_NAME[c.type] ?? c.type;
}

/**
 * Spec 035: one channel, like Chatwoot's inbox settings — a header with the
 * mark and state, and tabs: Ajustes · Agente · Plantillas (WhatsApp) · Salud.
 */
export default async function ChannelDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; channelId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id, channelId } = await params;
  const requested = (await searchParams).tab;
  const [channels, agents, connectors] = await Promise.all([
    backend.listChannels(id),
    backend.listTenantAgents(id).catch(() => []),
    backend.listTenantConnectors(id).catch(() => []),
  ]);
  const channel = channels.find((c) => c.id === channelId);
  if (!channel || channel.provider === "qa_playground") notFound();

  const isWhatsApp = channel.type === "whatsapp";
  const tabs: Array<{ key: Tab; label: string }> = [
    { key: "settings", label: "Ajustes" },
    { key: "agent", label: "Agente" },
    ...(isWhatsApp ? [{ key: "templates" as const, label: "Plantillas" }] : []),
    { key: "health", label: "Salud" },
  ];
  const tab: Tab = tabs.some((t) => t.key === requested) ? (requested as Tab) : "settings";
  const status = CHANNEL_STATUS[channel.status] ?? { label: channel.status, tone: "muted" as const };
  const role = channelRole(channel);
  const liveWhatsApp = channels.filter((c) => c.type === "whatsapp" && c.status !== "disconnected");
  const live = agents.filter((a) => a.status === "active");
  const principal = live.find((a) => a.is_principal);
  const agent = agents.find((a) => a.id === channel.agent_id) ?? principal ?? null;
  const connector = connectors.find((c) => c.connector_slug === CONNECTOR_OF[channel.type]);
  const base = `/tenants/${id}/channels/${channelId}`;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button nativeButton={false} variant="ghost" size="sm" render={<Link href={`/tenants/${id}/channels`} />}>
          <ArrowLeft aria-hidden="true" />
          Canales
        </Button>
      </div>
      <header className="flex flex-wrap items-center gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-md bg-muted">
          <ChannelIcon channel={channel.type} className="size-6" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="truncate text-lg font-semibold">{displayName(channel)}</h2>
          <p className="truncate text-sm text-muted-foreground">
            {CHANNEL_NAME[channel.type] ?? channel.type} · {channel.provider_identifier}
          </p>
        </div>
        <span className="inline-flex items-center gap-2 text-sm">
          <StatusDot tone={status.tone} />
          {status.label}
        </span>
      </header>

      <nav aria-label="Secciones del canal" className="flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <Link
            key={t.key}
            href={t.key === "settings" ? base : `${base}?tab=${t.key}`}
            aria-current={t.key === tab ? "page" : undefined}
            className={cn(
              "-mb-px border-b px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
              t.key === tab
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {tab === "settings" ? (
        channel.status === "disconnected" ? (
          <Callout tone="neutral" title="Este canal está retirado">
            Para volver a usarlo, conéctalo otra vez desde «Añadir canal».
          </Callout>
        ) : (
          <ChannelSettings
            tenantId={id}
            channelId={channel.id}
            showRole={isWhatsApp}
            soleNumber={liveWhatsApp.length <= 1}
            role={role}
            agentEnabled={channelAgentEnabled(channel)}
          />
        )
      ) : null}

      {tab === "agent" ? (
        live.length === 0 ? (
          <EmptyState
            title="Este cliente no tiene agentes activos"
            description="Crea su agente en la pestaña Agente del cliente."
            action={
              <Button nativeButton={false} render={<Link href={`/tenants/${id}/agent`} />}>
                Ir a Agente
              </Button>
            }
          />
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              {channel.agent_id
                ? `Atiende ${agent?.name ?? "un agente archivado"}.`
                : `Sin agente propio: atiende el principal${principal ? `, ${principal.name}` : ""}.`}
            </p>
            <ChannelAgentForm
              tenantId={id}
              channelId={channel.id}
              agents={live.map((a) => ({ id: a.id, label: a.is_principal && !/principal/i.test(a.name) ? `${a.name} (principal)` : a.name }))}
              current={channel.agent_id ?? principal?.id ?? ""}
            />
          </div>
        )
      ) : null}

      {tab === "templates" && isWhatsApp ? (
        <div className="flex flex-col gap-3">
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">
            Las plantillas son los mensajes que Meta aprueba para escribir primero: recordatorios, cobros y avisos. Se
            crean y se revisan en la cuenta de WhatsApp Business del cliente.
          </p>
          <div>
            <WhatsAppTemplatesDialog tenantId={id} />
          </div>
        </div>
      ) : null}

      {tab === "health" ? (
        <div className="flex flex-col gap-6">
          <DescriptionList
            columns={3}
            items={[
              { term: "Estado", detail: status.label },
              {
                term: "Última comprobación",
                detail: channel.last_health_check_at ? relativeTime(channel.last_health_check_at) : "Sin comprobar",
              },
              { term: "Conectado", detail: relativeTime(channel.created_at) },
              { term: "Proveedor", detail: channel.provider, mono: true },
              { term: "Identificador", detail: channel.provider_identifier, mono: true, truncate: true },
              { term: "Papel", detail: role ? ROLE_LABEL[role] : "Sin asignar" },
            ]}
          />
          {channel.status === "degraded" ? (
            <Callout tone="warning" title="El canal tiene problemas">
              El proveedor respondió con errores en la última comprobación. Prueba un envío y, si falla, vuelve a
              conectarlo.
            </Callout>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {isWhatsApp && channel.status !== "disconnected" ? <MetaTestSendDialog tenantId={id} /> : null}
            {connector && connector.status === "paused" ? (
              <ResumeConnectorButton
                tenantId={id}
                slug={connector.connector_slug}
                displayName={connector.connector_display_name}
              />
            ) : null}
            {connector && ["connected", "partial", "needs_reauth"].includes(connector.status) ? (
              <PauseConnectorButton
                tenantId={id}
                slug={connector.connector_slug}
                displayName={connector.connector_display_name}
              />
            ) : null}
            {connector && connector.status !== "disconnected" ? (
              <DisconnectButton
                tenantId={id}
                slug={connector.connector_slug}
                displayName={connector.connector_display_name}
              />
            ) : isWhatsApp ? (
              <>
                <MetaWhatsAppSetupDialog tenantId={id} alreadyConnected />
                <MetaConnectOwnedDialog tenantId={id} />
              </>
            ) : channel.type === "tiktok" ? (
              <TikTokConnectDialog tenantId={id} alreadyConnected />
            ) : null}
          </div>
          {connector ? (
            <p className="text-xs text-muted-foreground">
              Pausar o desconectar actúa sobre la conexión con {connector.connector_display_name}, no solo sobre este
              número.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
