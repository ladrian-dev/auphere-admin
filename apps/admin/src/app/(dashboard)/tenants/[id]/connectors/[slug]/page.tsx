import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Button, Callout, DescriptionList, Section, StatusDot } from "@nexus/ui";

import { ConnectorAuthBadge } from "@/components/brand/connector-auth-badge";
import { ConnectorLogo } from "@/components/brand/connector-logo";
import { AUTH_KIND_HINT, categoryName, connectorState, isChannelOnly } from "@/components/connectors/labels";
import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import {
  DisconnectButton,
  InitiateConsentButton,
  PauseConnectorButton,
  ReissueConsentButton,
  ResumeConnectorButton,
  SyncButton,
} from "../../_integrations/connector-actions";
import { AgendaProSetupDialog, WooCommerceSetupDialog } from "../../_integrations/setup-wizards";
import { ToolOverrides } from "./tool-overrides";

export const dynamic = "force-dynamic";

/**
 * Spec 035: one connector for one client, like Chatwoot's integration page —
 * what it is, its state, the actions that fit that state, and (new) what the
 * agent may do with each of its tools.
 */
export default async function TenantConnectorPage({ params }: { params: Promise<{ id: string; slug: string }> }) {
  const { id, slug: rawSlug } = await params;
  const slug = decodeURIComponent(rawSlug);
  const [connector, tenant, installed, tools, overrides] = await Promise.all([
    backend.getConnector(slug),
    backend.getTenant(id),
    backend.listTenantConnectors(id).catch(() => []),
    backend.listTenantToolCatalog(id, false).catch(() => []),
    backend.listConnectorToolOverrides(id).catch(() => []),
  ]);
  if (!connector || !tenant) notFound();
  // WhatsApp and TikTok are channels: their page is in Canales.
  if (isChannelOnly(connector)) redirect(`/tenants/${id}/channels`);

  const tc = installed.find((c) => c.connector_slug === slug) ?? null;
  const state = connectorState(tc?.status);
  const live = tc !== null && tc.status !== "disconnected";
  const isComposio = connector.auth_kind === "oauth_composio";
  const overrideOf = new Map(overrides.map((o) => [o.tool_name, o]));
  const ownTools = tools
    .filter((t) => t.connector_slug === slug)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((t) => ({
      name: t.name,
      description: t.description,
      destructive: t.destructive,
      readOnly: t.read_only,
      mode: overrideOf.get(t.name)?.mode ?? null,
      reason: overrideOf.get(t.name)?.reason ?? null,
    }));
  const common = { tenantId: id, slug, displayName: connector.display_name };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button nativeButton={false} variant="ghost" size="sm" render={<Link href={`/tenants/${id}/connectors`} />}>
          <ArrowLeft aria-hidden="true" />
          Conectores
        </Button>
      </div>

      <header className="flex flex-wrap items-center gap-4">
        <ConnectorLogo connector={connector} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            {connector.display_name}
            <ConnectorAuthBadge kind={connector.auth_kind} />
          </h2>
          <p className="text-sm text-muted-foreground">
            {connector.vendor} · {categoryName(connector.category)}
          </p>
        </div>
        <span className="inline-flex items-center gap-2 text-sm">
          <StatusDot tone={state.tone} />
          {state.label}
        </span>
      </header>

      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{AUTH_KIND_HINT[connector.auth_kind]}</p>

      {isComposio && !live && !tenant.owner_phone ? (
        <Callout tone="warning" title="Falta el teléfono del dueño">
          El enlace de permiso se manda por WhatsApp al dueño. Añade su teléfono en el Resumen del cliente.
        </Callout>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {!live ? (
          isComposio ? (
            <InitiateConsentButton {...common} ownerPhone={tenant.owner_phone} />
          ) : slug === "agendapro" ? (
            <AgendaProSetupDialog tenantId={id} currentUrl={tenant.agendapro_public_url} />
          ) : slug === "woocommerce" ? (
            <WooCommerceSetupDialog tenantId={id} alreadyConnected={false} />
          ) : (
            <p className="text-sm text-muted-foreground">Este conector se configura a mano con el equipo técnico.</p>
          )
        ) : (
          <>
            {tc.status === "pending" || tc.status === "needs_reauth" ? <ReissueConsentButton {...common} /> : null}
            {isComposio && tc.status === "connected" ? <SyncButton {...common} /> : null}
            {slug === "agendapro" ? (
              <AgendaProSetupDialog tenantId={id} currentUrl={tenant.agendapro_public_url} />
            ) : null}
            {slug === "woocommerce" ? <WooCommerceSetupDialog tenantId={id} alreadyConnected /> : null}
            {tc.status === "paused" ? <ResumeConnectorButton {...common} /> : null}
            {["connected", "partial", "needs_reauth"].includes(tc.status) ? <PauseConnectorButton {...common} /> : null}
            <DisconnectButton {...common} />
          </>
        )}
      </div>

      {tc ? (
        <DescriptionList
          columns={3}
          items={[
            { term: "Conectado", detail: tc.connected_at ? relativeTime(tc.connected_at) : "—" },
            { term: "Última sincronización", detail: tc.last_synced_at ? relativeTime(tc.last_synced_at) : "—" },
            {
              term: "Permisos concedidos",
              detail: tc.scopes_granted.length > 0 ? `${tc.scopes_granted.length}` : "—",
            },
            ...(tc.status === "pending" && tc.consent_token_expires_at
              ? [{ term: "El enlace caduca", detail: relativeTime(tc.consent_token_expires_at) }]
              : []),
          ]}
        />
      ) : null}

      <Section
        flat
        title="Qué puede hacer el agente"
        description="Cada herramienta sigue la regla por defecto salvo que la cambies aquí para este cliente: siempre, pide aprobación al dueño, o bloqueada."
      >
        <ToolOverrides tenantId={id} tools={ownTools} />
      </Section>
    </div>
  );
}
