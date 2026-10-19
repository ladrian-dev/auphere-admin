import { FlaskConical } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, Button, StatusDot } from "@nexus/ui";

import { ChannelLogo } from "@/components/brand/channel-logo";
import { CrumbName } from "@/components/shell/crumb-names";
import { TenantActionsMenu } from "@/components/tenants/tenant-actions-menu";
import { backend } from "@/lib/backend";
import { planLabel, relativeTime, statusLabel } from "@/lib/format";

import { TenantTabs } from "./tabs";

const STATUS_TONE = {
  active: "positive",
  paused: "warning",
  archived: "muted",
  provisioning: "warning",
} as const;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const tenant = await backend.getTenant(id).catch(() => null);
  return { title: tenant ? tenant.name : "Cliente" };
}

/**
 * Spec 036: the client's profile. The header answers «who is this and is it
 * working?» in one glance and fits in the top third of the screen (F-pattern):
 * name and state, one line of context, four facts with their shape (the
 * channel's logo and number, not «1»), and the most frequent task — trying
 * the agent — as the one primary button (Fitts). Tabs in one row below.
 */
export default async function TenantLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const tenant = await backend.getTenant(id);
  if (!tenant) notFound();
  const [partner, health] = await Promise.all([
    tenant.partner_id ? backend.getPartner(tenant.partner_id).catch(() => null) : null,
    backend.getTenantHealth(id).catch(() => null),
  ]);
  const base = `/tenants/${tenant.id}`;
  const channelTrouble = health ? health.channels_attention > 0 || health.channels_active === 0 : false;

  return (
    <div className="flex flex-col gap-6">
      <CrumbName id={tenant.id} label={tenant.name} />
      <header className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-balance md:text-3xl">{tenant.name}</h1>
              <span className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs font-medium">
                <StatusDot tone={STATUS_TONE[tenant.status] ?? "muted"} />
                {statusLabel(tenant.status)}
              </span>
            </div>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              {/* Spec 031 (R5.3): whose client this is, one click away. */}
              {partner ? (
                <Link href={`/partners/${partner.id}`} className="underline-offset-4 hover:text-foreground hover:underline">
                  {partner.name}
                </Link>
              ) : (
                <span>Cliente directo de Auphere</span>
              )}
              <span aria-hidden="true">·</span>
              <Badge variant="outline">{planLabel(tenant.plan)}</Badge>
              {tenant.market ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{tenant.market}</span>
                </>
              ) : null}
              <span aria-hidden="true">·</span>
              <span>{tenant.timezone}</span>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button nativeButton={false} render={<Link href={`${base}/playground`} />}>
              <FlaskConical aria-hidden="true" />
              Probar agente
            </Button>
            <TenantActionsMenu
              tenantId={tenant.id}
              slug={tenant.slug}
              name={tenant.name}
              status={tenant.status}
              variant="labelled"
              redirectAfterDeleteTo="/tenants"
            />
          </div>
        </div>

        <ul aria-label="Datos clave" className="grid grid-cols-2 gap-px overflow-hidden rounded-md bg-border ring-1 ring-border lg:grid-cols-4">
          <Fact term="Canal" href={health?.primary_channel ? `${base}/channels` : `${base}/channels/new`}>
            {health?.primary_channel ? (
              <span className="flex min-w-0 items-center gap-2">
                <ChannelLogo channel={health.primary_channel.type} size="sm" />
                <span className="truncate font-mono text-sm">{health.primary_channel.identifier}</span>
                {health.channels_active > 1 ? (
                  <span className="text-xs text-muted-foreground">+{health.channels_active - 1}</span>
                ) : null}
              </span>
            ) : (
              <span className="text-status-warning-text">{health ? "Sin canal · Añadir" : "—"}</span>
            )}
          </Fact>
          <Fact term="Agente" href={`${base}/agent`}>
            {health ? (
              health.agent_version !== null ? (
                `Versión ${health.agent_version}`
              ) : (
                <span className="text-status-warning-text">Sin publicar</span>
              )
            ) : (
              "—"
            )}
          </Fact>
          <Fact term="Última conversación" href={`${base}/conversations`}>
            {health?.last_message_at ? relativeTime(health.last_message_at) : "Sin mensajes"}
          </Fact>
          <Fact term="Esta semana" href={`${base}/conversations`}>
            {health ? (
              <span className="tabular-nums">
                {health.conversations_7d} {health.conversations_7d === 1 ? "conversación" : "conversaciones"}
                {health.open_conversations > 0 ? (
                  <span className="text-muted-foreground"> · {health.open_conversations} abiertas</span>
                ) : null}
              </span>
            ) : (
              "—"
            )}
          </Fact>
        </ul>
      </header>
      <TenantTabs tenantId={tenant.id} channelsMark={channelTrouble ? "incident" : undefined} />
      {children}
    </div>
  );
}

/** One fact of the header: a label and its value, the whole cell a link. */
function Fact({ term, href, children }: { term: string; href: string; children: React.ReactNode }) {
  return (
    <li className="flex">
      <Link
        href={href}
        className="flex w-full min-w-0 flex-col gap-1 bg-card px-4 py-3 outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <span className="text-xs text-muted-foreground">{term}</span>
        <span className="truncate text-sm font-medium">{children}</span>
      </Link>
    </li>
  );
}
