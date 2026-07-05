import Link from "next/link";

import { Eyebrow } from "@/components/brand/eyebrow";
import { ReadinessCard } from "@/components/tenants/readiness-card";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { requireSession } from "@/lib/session";

export default async function TenantOverview({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await requireSession();
  const operatorId = session.user.id;

  const [tenant, agentBundle, recentThreads, readiness] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id),
    // Best-effort fetch — if /qa/* is misconfigured we still render the page.
    qaApi
      .listThreads({ operatorId, tenantId: id, limit: 5 })
      .catch(() => [] as QAThread[]),
    // Best-effort — a readiness failure must not break the overview.
    backend.getReadiness(id).catch(() => null),
  ]);
  if (!tenant) return null;

  const activeVersion = agentBundle.active?.version;
  const totalVersions = agentBundle.versions.length;
  const whitelistSize = agentBundle.active?.tools.length ?? 0;
  const channelsCount = (agentBundle.active?.channels ?? []).length;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Go-live readiness — full width, top of the grid */}
      <ReadinessCard readiness={readiness} />

      {/* Identity */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <Eyebrow>Identidad</Eyebrow>
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
          <Eyebrow>Agente</Eyebrow>
          <CardTitle>
            {activeVersion
              ? `Versión ${activeVersion} activa`
              : "Sin versión activa"}
          </CardTitle>
          <CardDescription>
            {activeVersion
              ? `${totalVersions} versión${totalVersions === 1 ? "" : "es"} en historial · ${whitelistSize} tools en whitelist`
              : "Crea una primera versión desde la pestaña Agente."}
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
          <Eyebrow>Salud operativa</Eyebrow>
          <CardTitle>Indicadores</CardTitle>
          <CardDescription>
            Resumen rápido. Entrá a las pestañas de aislamiento o connectors
            para el detalle completo.
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
            href={`/tenants/${tenant.id}/connectors`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Estado de connectors →
          </Link>
          <Link
            href={`/tenants/${tenant.id}/isolation`}
            className="text-sm text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1"
          >
            Garantías de aislamiento →
          </Link>
        </CardContent>
      </Card>

      {/* Probar agente — ADR-020 Phase 5 entry point */}
      <Card className="lg:col-span-3">
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <Eyebrow>QA Playground</Eyebrow>
            <CardTitle>Probar agente</CardTitle>
            <CardDescription>
              Conversá con el agente como si fueras el cliente, en sandbox
              dry-run. Ningún side-effect real se ejecuta; los tool calls
              quedan auditados.
            </CardDescription>
          </div>
          <Link
            href={`/qa/${tenant.id}/chat`}
            className="inline-flex items-center justify-center rounded-md bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-[color:var(--color-on-primary,#fff)] hover:opacity-90"
          >
            Abrir Playground →
          </Link>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          {recentThreads.length === 0 ? (
            <span className="text-muted-foreground">
              Sin conversaciones QA todavía.
            </span>
          ) : (
            <>
              <span className="text-xs font-mono uppercase text-muted-foreground">
                Conversaciones QA recientes
              </span>
              <ul className="grid gap-1">
                {recentThreads.map((t) => (
                  <li key={t.id} className="flex items-center justify-between">
                    <Link
                      href={`/qa/${tenant.id}/chat?thread=${t.id}`}
                      className="hover:underline underline-offset-4 decoration-1"
                    >
                      {t.title}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {relativeTime(t.updated_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
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
