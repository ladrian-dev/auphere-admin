import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, StatusDot } from "@nexus/ui";

import { TenantActionsMenu } from "@/components/tenants/tenant-actions-menu";
import { CrumbName } from "@/components/shell/crumb-names";
import { backend } from "@/lib/backend";
import { planLabel, statusLabel } from "@/lib/format";

import { TenantTabs } from "./tabs";

const STATUS_TONE = {
  active: "positive",
  paused: "warning",
  archived: "muted",
} as const;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const tenant = await backend.getTenant(id).catch(() => null);
  return { title: tenant ? tenant.name : "Cliente" };
}

/**
 * The client's profile, built like the partner's (spec 031 R4.3): the name,
 * one line of who and what, the facts the operator asks first, and the tabs
 * grouped like the partner console's client page. The trail lives in the top
 * bar, so the page does not repeat «Clientes / slug» nor say «Cliente».
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
  const [partner, channels, connectors, agent] = await Promise.all([
    tenant.partner_id ? backend.getPartner(tenant.partner_id).catch(() => null) : null,
    backend.listChannels(id).catch(() => null),
    backend.listTenantConnectors(id).catch(() => null),
    backend.getAgentConfig(id).catch(() => null),
  ]);

  const realChannels = channels?.filter((c) => c.provider !== "qa_playground") ?? null;
  const liveChannels = realChannels?.filter((c) => c.status === "active") ?? null;
  const brokenChannel = realChannels?.some((c) => c.status === "degraded") ?? false;
  const liveConnectors = connectors?.filter((c) => c.status === "connected" || c.status === "partial") ?? null;
  const base = `/tenants/${tenant.id}`;

  const facts = [
    {
      term: "Canales activos",
      detail: liveChannels ? liveChannels.length : "—",
      href: `${base}/channels`,
    },
    {
      term: "Conectores activados",
      detail: liveConnectors ? liveConnectors.length : "—",
      href: `${base}/connectors`,
    },
    {
      term: "Agente",
      detail: agent?.active ? `Versión ${agent.active.version}` : "Sin publicar",
      href: `${base}/agent`,
    },
    {
      term: "Alta",
      detail: new Date(tenant.created_at).toLocaleDateString("es", { dateStyle: "medium" }),
      href: null,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <CrumbName id={tenant.id} label={tenant.name} />
      <header className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-balance md:text-3xl">{tenant.name}</h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-2">
                <StatusDot tone={STATUS_TONE[tenant.status]} />
                {statusLabel(tenant.status)}
              </span>
              <Badge variant="outline">{planLabel(tenant.plan)}</Badge>
              {/* Spec 031 (R5.3): whose client this is, one click away. */}
              {partner ? (
                <Link href={`/partners/${partner.id}`} className="underline-offset-4 hover:text-foreground hover:underline">
                  {partner.name}
                </Link>
              ) : (
                <span>Cliente directo de Auphere</span>
              )}
              {tenant.market ? <span>{tenant.market}</span> : null}
              <span>{tenant.timezone}</span>
              <span className="font-mono text-xs">{tenant.slug}</span>
            </div>
          </div>
          <TenantActionsMenu
            tenantId={tenant.id}
            slug={tenant.slug}
            name={tenant.name}
            status={tenant.status}
            variant="labelled"
            redirectAfterDeleteTo="/tenants"
          />
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          {facts.map((f) => (
            <div key={f.term} className="flex min-w-0 flex-col gap-1">
              <dt className="text-xs text-muted-foreground">{f.term}</dt>
              <dd className="truncate text-base font-semibold tabular-nums">
                {f.href ? (
                  <Link href={f.href} className="underline-offset-4 hover:underline">
                    {f.detail}
                  </Link>
                ) : (
                  f.detail
                )}
              </dd>
            </div>
          ))}
        </dl>
      </header>
      <TenantTabs
        tenantId={tenant.id}
        channelsMark={brokenChannel || (liveChannels !== null && liveChannels.length === 0) ? "incident" : undefined}
      />
      {children}
    </div>
  );
}
