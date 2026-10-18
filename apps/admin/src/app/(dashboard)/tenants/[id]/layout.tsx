import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, Eyebrow, Separator, StatusDot } from "@nexus/ui";
import { backend } from "@/lib/backend";
import { planLabel, statusLabel } from "@/lib/format";

import { TenantActionsMenu } from "@/components/tenants/tenant-actions-menu";

import { TenantTabs } from "./tabs";

const STATUS_TONE = {
  active: "positive",
  paused: "warning",
  archived: "muted",
} as const;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const tenant = await backend.getTenant(id).catch(() => null);
  return {
    title: tenant ? tenant.name : "Tenant",
  };
}

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
  const partner = tenant.partner_id ? await backend.getPartner(tenant.partner_id).catch(() => null) : null;

  return (
    <>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <nav
            aria-label="Migas"
            className="flex items-center gap-2 text-xs font-mono uppercase text-muted-foreground tracking-eyebrow"
          >
            <Link
              href="/tenants"
              className="hover:text-foreground transition-colors"
            >
              Clientes
            </Link>
            <span aria-hidden="true">/</span>
            <span className="text-foreground">{tenant.slug}</span>
          </nav>
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="flex flex-col gap-2">
              <Eyebrow>Cliente</Eyebrow>
              <h1
                className="text-2xl md:text-3xl font-semibold leading-tight tracking-tight"
              >
                {tenant.name}
              </h1>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <Badge variant="outline">{planLabel(tenant.plan)}</Badge>
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone={STATUS_TONE[tenant.status]} />
                  {statusLabel(tenant.status)}
                </span>
                {/* Spec 031 (R5.3): whose client this is, one click away. */}
                {partner ? (
                  <Link href={`/partners/${partner.id}`} className="underline-offset-4 hover:underline">
                    Partner: {partner.name}
                  </Link>
                ) : (
                  <span>Cliente directo de Auphere</span>
                )}
                {tenant.market ? <span>{tenant.market}</span> : null}
                <span className="font-mono">{tenant.timezone}</span>
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
        </div>
        <TenantTabs tenantId={tenant.id} />
        <Separator />
        {children}
      </div>
    </>
  );
}
