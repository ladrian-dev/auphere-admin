import type { Tenant, TenantHealth } from "@/lib/backend";

export type ReadinessCheck = {
  key: string;
  ok: boolean;
  label: string;
  detail: string;
  href?: string;
  action?: string;
};

/**
 * Spec 036: what stands between a client and real customers, worked out from
 * what the panel already reads. Pure, so it is tested on its own. The order is
 * the order of the setup: agent, channel, owner, connectors.
 */
export function readinessChecks({
  base,
  tenant,
  health,
  brokenConnectors,
}: {
  base: string;
  tenant: Pick<Tenant, "owner_phone">;
  health: TenantHealth | null;
  brokenConnectors: string[];
}): ReadinessCheck[] {
  const live = health?.channels_active ?? 0;
  const version = health?.agent_version ?? null;
  return [
    {
      key: "agent",
      ok: version !== null,
      label: version !== null ? "Agente publicado" : "Publicar el agente",
      detail: version !== null ? `Responde con la versión ${version}.` : "Todavía no hay una versión publicada.",
      href: `${base}/agent`,
      action: "Abrir Agente",
    },
    {
      key: "channel",
      ok: live > 0,
      label: live > 0 ? "Canal activo" : "Conectar un canal",
      detail:
        live > 0
          ? `${live} ${live === 1 ? "canal atiende" : "canales atienden"} a sus clientes.`
          : health && health.channels_attention > 0
            ? "Su canal tiene problemas y no atiende."
            : "Ningún canal está conectado.",
      href: live > 0 || (health?.channels_attention ?? 0) > 0 ? `${base}/channels` : `${base}/channels/new`,
      action: live > 0 ? "Ver canales" : (health?.channels_attention ?? 0) > 0 ? "Revisar canal" : "Añadir canal",
    },
    {
      key: "owner",
      ok: Boolean(tenant.owner_phone),
      label: tenant.owner_phone ? "Teléfono del dueño" : "Añadir el teléfono del dueño",
      detail: tenant.owner_phone
        ? "Recibe los avisos y los enlaces de permiso por WhatsApp."
        : "Sin él no le llegan avisos ni los enlaces para conectar apps. Se añade desde Acciones.",
    },
    {
      key: "connectors",
      ok: brokenConnectors.length === 0,
      label: brokenConnectors.length === 0 ? "Conectores en orden" : "Reconectar conectores",
      detail:
        brokenConnectors.length === 0
          ? "Ningún conector pide atención."
          : `${brokenConnectors.join(", ")} ${brokenConnectors.length === 1 ? "necesita" : "necesitan"} volver a conectarse.`,
      href: `${base}/connectors`,
      action: "Ver conectores",
    },
  ];
}
