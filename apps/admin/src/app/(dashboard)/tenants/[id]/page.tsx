import { Check, CircleAlert } from "lucide-react";
import Link from "next/link";

import { Button, DescriptionList, Section } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { requireOperator } from "@/lib/session";
import { cn } from "@/lib/utils";

type Check = { key: string; ok: boolean; label: string; detail: string; href?: string; action?: string };

/**
 * The client's summary, laid out like the partner's (spec 031 R4.3): what
 * stands between the client and real customers, who they are, their agent,
 * and the playground. The checklist is worked out here from what the panel
 * already reads — the old readiness endpoint is gone.
 */
export default async function TenantOverview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const operator = await requireOperator();
  const [tenant, agent, channels, connectors, threads] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id).catch(() => null),
    backend.listChannels(id).catch(() => null),
    backend.listTenantConnectors(id).catch(() => null),
    qaApi.listThreads({ operatorId: operator.id, tenantId: id, limit: 5 }).catch(() => [] as QAThread[]),
  ]);
  if (!tenant) return null;
  const partner = tenant.partner_id ? await backend.getPartner(tenant.partner_id).catch(() => null) : null;

  const base = `/tenants/${id}`;
  const live = channels?.filter((c) => c.provider !== "qa_playground" && c.status === "active") ?? [];
  const broken = connectors?.filter((c) => c.status === "needs_reauth" || c.status === "error") ?? [];
  const checks: Check[] = [
    {
      key: "agent",
      ok: Boolean(agent?.active),
      label: "Agente publicado",
      detail: agent?.active ? `Responde con la versión ${agent.active.version}.` : "Todavía no hay una versión publicada.",
      href: `${base}/agent`,
      action: "Abrir Agente",
    },
    {
      key: "channel",
      ok: live.length > 0,
      label: "Canal activo",
      detail:
        live.length > 0
          ? `${live.length} ${live.length === 1 ? "canal atiende" : "canales atienden"} a sus clientes.`
          : "Ningún canal está conectado y activo.",
      href: live.length > 0 ? `${base}/channels` : `${base}/channels/new`,
      action: live.length > 0 ? "Ver canales" : "Añadir canal",
    },
    {
      key: "owner",
      ok: Boolean(tenant.owner_phone),
      label: "Teléfono del dueño",
      detail: tenant.owner_phone
        ? "Recibe los avisos y los enlaces de permiso por WhatsApp."
        : "Sin él no le llegan avisos ni los enlaces para conectar apps. Añádelo desde Acciones.",
    },
    {
      key: "connectors",
      ok: broken.length === 0,
      label: "Conectores sin problemas",
      detail:
        broken.length === 0
          ? "Ningún conector pide atención."
          : `${broken.map((c) => c.connector_display_name).join(", ")} ${broken.length === 1 ? "necesita" : "necesitan"} volver a conectarse.`,
      href: `${base}/connectors`,
      action: "Ver conectores",
    },
  ];
  const pending = checks.filter((c) => !c.ok).length;

  return (
    <div className="grid gap-6">
      <Section
        title={pending === 0 ? "Listo para operar" : "Faltan pasos para operar"}
        description={
          pending === 0
            ? "Este cliente puede atender a clientes reales."
            : `${pending} ${pending === 1 ? "paso pendiente" : "pasos pendientes"} antes de atender a clientes reales.`
        }
        padded={false}
      >
        <ul className="divide-y divide-border">
          {checks.map((c) => (
            <li key={c.key} className="flex items-start gap-3 px-6 py-3">
              {c.ok ? (
                <Check className="mt-1 size-4 shrink-0 text-status-positive-text" aria-hidden="true" />
              ) : (
                <CircleAlert className="mt-1 size-4 shrink-0 text-status-warning-text" aria-hidden="true" />
              )}
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-sm font-medium">
                  {c.label}
                  <span className="sr-only">{c.ok ? ": hecho" : ": pendiente"}</span>
                </span>
                <span className="text-sm text-pretty text-muted-foreground">{c.detail}</span>
              </div>
              {c.href && c.action ? (
                <Link
                  href={c.href}
                  className={cn(
                    "shrink-0 text-sm underline-offset-4 hover:underline",
                    c.ok ? "text-muted-foreground" : "text-primary-deep",
                  )}
                >
                  {c.action}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Datos del cliente" description="Quién es y cómo se le escribe. Se editan desde Acciones.">
        <DescriptionList
          columns={3}
          items={[
            { key: "name", term: "Nombre", detail: tenant.name },
            { key: "slug", term: "Identificador", detail: tenant.slug, mono: true },
            {
              key: "partner",
              term: "Partner",
              detail: partner ? (
                <Link href={`/partners/${partner.id}`} className="underline-offset-4 hover:underline">
                  {partner.name}
                </Link>
              ) : (
                "Cliente directo de Auphere"
              ),
            },
            { key: "email", term: "Correo del dueño", detail: tenant.owner_email ?? "—", truncate: true },
            { key: "phone", term: "Teléfono del dueño", detail: tenant.owner_phone ?? "—", mono: true },
            { key: "market", term: "Mercado", detail: tenant.market ?? "—" },
            { key: "tz", term: "Zona horaria", detail: tenant.timezone },
            { key: "created", term: "Alta", detail: fullDateTime(tenant.created_at) },
            { key: "updated", term: "Última modificación", detail: relativeTime(tenant.updated_at) },
          ]}
        />
      </Section>

      <Section
        title="Agente"
        description="La versión que responde hoy y su historial."
        actions={
          <Button nativeButton={false} variant="outline" size="sm" render={<Link href={`${base}/agent`} />}>
            Abrir Agente
          </Button>
        }
      >
        <DescriptionList
          columns={3}
          items={[
            { key: "version", term: "Versión activa", detail: agent?.active ? `Versión ${agent.active.version}` : "Sin publicar" },
            { key: "versions", term: "Versiones guardadas", detail: agent ? agent.versions.length : "—" },
            { key: "tools", term: "Herramientas activas", detail: agent?.active ? agent.active.tools.length : "—" },
            {
              key: "promoted",
              term: "Publicada",
              detail: agent?.active?.promoted_at ? relativeTime(agent.active.promoted_at) : "—",
            },
          ]}
        />
      </Section>

      <Section
        title="Playground QA"
        description="Habla con el agente como si fueras un cliente. Nada sale de verdad y cada herramienta queda auditada."
        actions={
          <Button nativeButton={false} size="sm" render={<Link href={`/qa/${tenant.id}/chat`} />}>
            Abrir Playground
          </Button>
        }
      >
        {threads.length === 0 ? (
          <p className="text-sm text-muted-foreground">Todavía no hay conversaciones de prueba.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {threads.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-4 py-2">
                <Link href={`/qa/${tenant.id}/chat?thread=${t.id}`} className="truncate text-sm underline-offset-4 hover:underline">
                  {t.title}
                </Link>
                <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(t.updated_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
