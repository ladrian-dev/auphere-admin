import type { MembershipOut, SendReadinessOut, Tenant, TenantHealth } from "@/lib/backend";
import { formatCents } from "@/lib/format";

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

/** Spec 077: a step of a send-only client's setup. `unknown`: it could not be checked. */
export type SendStep = ReadinessCheck & { state: "done" | "todo" | "unknown" };

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * Spec 077 (1.4): what a send-only client needs before its API sends, from
 * `GET /admin/tenants/{id}/send-readiness`. Pure, so it is tested on its own.
 * Number, authentication template, membership (only when it has one) and an
 * active key. A template Meta did not answer about is neither ready nor
 * pending: it is said as «no se pudo comprobar».
 */
export function sendReadinessChecks({
  base,
  readiness,
  membership,
}: {
  base: string;
  readiness: SendReadinessOut;
  /** Optional: with it the membership step says the amount and who pays. */
  membership?: Pick<MembershipOut, "amount_cents" | "payer"> | null;
}): SendStep[] {
  const { channel, template, keys } = readiness;
  const steps: SendStep[] = [];

  steps.push(
    channel.ok
      ? {
          key: "channel",
          state: "done",
          ok: true,
          label: "Número conectado",
          detail: `${plural(channel.active_numbers, "número activo", "números activos")}, sin agente que responda.`,
          href: `${base}/channels`,
          action: "Ver canales",
        }
      : {
          key: "channel",
          state: "todo",
          ok: false,
          label: "Conectar su número de WhatsApp",
          detail: "Entra con su cuenta de Meta y elige su número. Lo de Meta lo paga él.",
          href: `${base}/channels/new/whatsapp`,
          action: "Enviar enlace",
        },
  );

  if (!channel.ok) {
    steps.push({
      key: "template",
      state: "todo",
      ok: false,
      label: "Plantilla de código",
      detail: "Autenticación, aprobada por Meta. Se crea en su número, cuando esté conectado.",
    });
  } else if (template.unknown) {
    steps.push({
      key: "template",
      state: "unknown",
      ok: false,
      label: "Plantilla de código",
      detail: "No se pudo comprobar: Meta no respondió. Vuelve a cargar en unos minutos.",
      href: `${base}/channels`,
      action: "Ver plantillas",
    });
  } else if (template.ok) {
    steps.push({
      key: "template",
      state: "done",
      ok: true,
      label: "Plantilla de código aprobada",
      detail: `${plural(template.approved, "plantilla de autenticación aprobada", "plantillas de autenticación aprobadas")} por Meta.`,
      href: `${base}/channels`,
      action: "Ver plantillas",
    });
  } else {
    steps.push({
      key: "template",
      state: "todo",
      ok: false,
      label: "Plantilla de código",
      detail:
        template.pending > 0
          ? `${plural(template.pending, "plantilla de autenticación", "plantillas de autenticación")} en revisión de Meta.`
          : "Autenticación, aprobada por Meta.",
      href: `${base}/channels`,
      action: template.pending > 0 ? "Ver plantillas" : "Crear plantilla",
    });
  }

  // The absence is designed: without a membership there is no step.
  if (readiness.membership) {
    const m = readiness.membership;
    const amount = membership ? `${formatCents(membership.amount_cents)} al mes ${membership.payer === "stripe" ? "por Stripe" : "del saldo del partner"}. ` : "";
    const detail =
      m.ok
        ? `${amount}Al día: los envíos salen.`
        : m.status === "pending"
          ? `${amount}Pendiente del primer pago.`
          : m.status === "past_due"
            ? `${amount}Impagada: la API no envía.`
            : m.status === "canceled"
              ? `${amount}Cancelada: la API no envía.`
              : `${amount}Sin cobrar este periodo: la API no envía.`;
    steps.push({
      key: "membership",
      state: m.ok ? "done" : "todo",
      ok: m.ok,
      label: m.ok ? "Membresía activa" : "Membresía",
      detail,
      href: `${base}/billing`,
      action: m.ok ? "Ver Facturación" : m.status === "pending" && membership?.payer === "stripe" ? "Crear enlace de pago" : "Abrir Facturación",
    });
  }

  steps.push(
    keys.ok
      ? {
          key: "keys",
          state: "done",
          ok: true,
          label: "Clave activa",
          detail: `${plural(keys.active, "clave activa", "claves activas")} para llamar a la API.`,
          href: `${base}/api`,
          action: "Ver claves",
        }
      : {
          key: "keys",
          state: "todo",
          ok: false,
          label: "Clave de acceso",
          detail: "La que usa su sistema para llamar a la API.",
          href: `${base}/api`,
          action: "Crear clave",
        },
  );
  return steps;
}
