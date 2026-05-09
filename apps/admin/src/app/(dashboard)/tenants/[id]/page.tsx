import Link from "next/link";

import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";

export default async function TenantOverview({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, agentBundle] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id),
  ]);
  if (!tenant) return null;

  const activeVersion = agentBundle.active?.version;
  const totalVersions = agentBundle.versions.length;
  const whitelistSize = agentBundle.active?.tools.length ?? 0;
  const channelsCount = (agentBundle.active?.channels ?? []).length;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Identity */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <Eyebrow index="01">Identidad</Eyebrow>
          <CardTitle>{tenant.name}</CardTitle>
          <CardDescription className="font-mono">{tenant.slug}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <Row label="Mercado" value={tenant.market ?? "—"} />
          <Row label="Zona horaria" value={tenant.timezone} mono />
          <Row label="Owner email" value={tenant.owner_email ?? "—"} />
          <Row label="Owner phone" value={tenant.owner_phone ?? "—"} mono />
          <Row label="Creado" value={fullDateTime(tenant.created_at)} />
          <Row label="Actualizado" value={relativeTime(tenant.updated_at)} />
        </CardContent>
      </Card>

      {/* Agent state */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <Eyebrow index="02">Agente</Eyebrow>
          <CardTitle>
            {activeVersion
              ? `Versión ${activeVersion} activa`
              : "Sin versión activa"}
          </CardTitle>
          <CardDescription>
            {activeVersion
              ? `${totalVersions} versión${totalVersions === 1 ? "" : "es"} en historial · ${whitelistSize} tools en whitelist`
              : "Agendá una primera versión desde la pestaña Agente."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <Row
            label="Canales"
            value={channelsCount === 0 ? "—" : `${channelsCount} canal${channelsCount === 1 ? "" : "es"}`}
          />
          <Row
            label="Última promoción"
            value={
              agentBundle.active?.promoted_at
                ? relativeTime(agentBundle.active.promoted_at)
                : "—"
            }
          />
          <Link
            href={`/tenants/${tenant.id}/agent`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Editar agente →
          </Link>
        </CardContent>
      </Card>

      {/* Quick actions / signals */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <Eyebrow index="03">Salud operativa</Eyebrow>
          <CardTitle>Signals</CardTitle>
          <CardDescription>
            Resumen rápido. Para detalle entrá a la pestaña de aislamiento o
            integraciones.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <Link
            href={`/tenants/${tenant.id}/conversations`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Ver conversaciones en vivo →
          </Link>
          <Link
            href={`/tenants/${tenant.id}/integrations`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Estado de integraciones →
          </Link>
          <Link
            href={`/tenants/${tenant.id}/isolation`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Garantías de aislamiento →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[1fr_2fr] items-baseline gap-3 border-b border-border last:border-b-0 pb-2 last:pb-0">
      <span className="text-xs font-mono uppercase text-muted-foreground"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        {label}
      </span>
      <span className={mono ? "font-mono" : undefined}>{value}</span>
    </div>
  );
}
