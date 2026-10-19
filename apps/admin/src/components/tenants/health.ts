/**
 * Spec 036: how the client list reads each client's health. Pure, so the
 * list and its tests share it.
 *
 * A client «needs attention» when something stands between it and its
 * customers, or between it and the operator's next step. Each reason is said
 * in words (H2) and only these rows stand out (Von Restorff).
 */
import type { Tenant, TenantHealth } from "@/lib/backend";

export type Reason = { key: string; label: string; tone: "danger" | "warning" };

/** A client is quiet when it serves but nobody has written in this long. */
export const QUIET_DAYS = 14;

export function reasonsFor(tenant: Pick<Tenant, "status">, health: TenantHealth | undefined): Reason[] {
  if (tenant.status === "archived" || tenant.status === "paused") return [];
  if (tenant.status === "provisioning") return [{ key: "provisioning", label: "A medio montar", tone: "warning" }];
  if (!health) return [];
  const out: Reason[] = [];
  if (health.channels_attention > 0) out.push({ key: "channel_down", label: "Canal con problemas", tone: "danger" });
  if (health.connectors_attention > 0) out.push({ key: "connector", label: "Conector por reconectar", tone: "danger" });
  if (health.channels_active === 0 && health.channels_attention === 0) {
    out.push({ key: "no_channel", label: "Sin canal", tone: "warning" });
  }
  if (health.agent_version === null) out.push({ key: "no_agent", label: "Agente sin publicar", tone: "warning" });
  return out;
}

/**
 * A client that serves but nobody has written to in a while. A soft hint for
 * the activity column, not a reason: on a quiet week it would mark every row
 * and drown the ones that are really broken.
 */
export function isQuiet(health: TenantHealth | undefined, now = Date.now()): boolean {
  return Boolean(
    health &&
      health.channels_active > 0 &&
      health.last_message_at &&
      now - new Date(health.last_message_at).getTime() > QUIET_DAYS * 86_400_000,
  );
}

export type View = "all" | "attention" | "active" | "paused" | "archived";

export const VIEWS: Array<{ key: View; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "attention", label: "Necesitan atención" },
  { key: "active", label: "Activos" },
  { key: "paused", label: "En pausa" },
  { key: "archived", label: "Archivados" },
];

export function inView(view: View, tenant: Pick<Tenant, "status">, reasons: Reason[]): boolean {
  switch (view) {
    case "all":
      // Archived clients are history: out of the default view, one tab away.
      return tenant.status !== "archived";
    case "attention":
      return reasons.length > 0;
    case "active":
      return tenant.status === "active";
    case "paused":
      return tenant.status === "paused";
    case "archived":
      return tenant.status === "archived";
  }
}

export type Sort = "attention" | "name" | "activity";

export const SORTS: Array<{ key: Sort; label: string }> = [
  { key: "attention", label: "Lo urgente primero" },
  { key: "activity", label: "Actividad reciente" },
  { key: "name", label: "Nombre" },
];

type Row = { tenant: Pick<Tenant, "name">; reasons: Reason[]; health?: TenantHealth };

const weight = (r: Reason[]) => (r.some((x) => x.tone === "danger") ? 2 : r.length > 0 ? 1 : 0);
const activity = (h?: TenantHealth) => (h?.last_message_at ? new Date(h.last_message_at).getTime() : 0);

export function compareRows(sort: Sort) {
  return (a: Row, b: Row): number => {
    const byName = a.tenant.name.localeCompare(b.tenant.name, "es");
    if (sort === "name") return byName;
    if (sort === "activity") return activity(b.health) - activity(a.health) || byName;
    return weight(b.reasons) - weight(a.reasons) || byName;
  };
}
