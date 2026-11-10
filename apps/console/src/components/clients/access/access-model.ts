import type { MessageKey } from "@/i18n/messages";
import {
  ACCESS_MODULES,
  type AccessModule,
  type CapacityKind,
  type ClientAccess,
  type ClientAccessIn,
  type ClientAccessMember,
  type ReservasMode,
} from "@/lib/backend/client-access";

/**
 * Spec 056 (Requisito 3) — las cuentas puras de la pestaña «Acceso». Sin React:
 * se prueban solas. La lógica es la de la pestaña Acceso del panel
 * (`apps/admin/.../access/access-form.tsx`), portada aquí porque vive en otro
 * workspace de pnpm y no se comparte. Las reglas de verdad son de la API.
 */

export type PersonAction = "resend" | "revoke";

/**
 * Una acción principal por fila y el resto en «⋯» (guías de Apple, como
 * `connector-model.rowLayout`): Reenviar a una invitada o caducada; Revocar,
 * siempre la última. Lo revocado ya no tiene nada que hacer.
 */
export function personRowLayout(m: ClientAccessMember): { primary: PersonAction | null; menu: PersonAction[] } {
  if (m.status === "revoked") return { primary: null, menu: [] };
  if (m.kind === "invitation") {
    if (m.status === "pending") return { primary: "resend", menu: ["revoke"] };
    if (m.status === "expired") return { primary: "resend", menu: [] };
    return { primary: null, menu: [] };
  }
  return m.status === "active" ? { primary: null, menu: ["revoke"] } : { primary: null, menu: [] };
}

export type StatusTone = "positive" | "info" | "warn" | "muted";

/** Invitada, activa, caducada o revocada (3.4), con su tono. */
export function personStatus(m: ClientAccessMember): { key: MessageKey; tone: StatusTone } {
  switch (m.status) {
    case "active":
      return { key: "clientAccess.status.active", tone: "positive" };
    case "pending":
      return { key: "clientAccess.status.pending", tone: "info" };
    case "expired":
      return { key: "clientAccess.status.expired", tone: "warn" };
    default:
      return { key: "clientAccess.status.revoked", tone: "muted" };
  }
}

/** Lo que pide el diálogo de Revocar: a una persona se le cierra todo, a una invitación se le mata el enlace. */
export function revokeCopy(m: ClientAccessMember): { title: MessageKey; body: MessageKey } {
  return m.kind === "member"
    ? { title: "clientAccess.revoke.member.title", body: "clientAccess.revoke.member.body" }
    : { title: "clientAccess.revoke.invitation.title", body: "clientAccess.revoke.invitation.body" };
}

export type AccessDraft = {
  enabled: boolean;
  modules: ReadonlySet<string>;
  mode: ReservasMode | null;
  kind: CapacityKind | null;
};

/** Los módulos de la tarjeta, en el orden de la barra del cliente. */
export function orderedModules(modules: ReadonlySet<string>): AccessModule[] {
  return ACCESS_MODULES.filter((m) => modules.has(m));
}

/**
 * ¿Cambian los ajustes de Reservas? La primera vez que se enciende, o si cambia
 * su modo o su tipo. Si no, no se vuelven a mandar.
 */
export function reservasDirty(stored: ClientAccess, draft: AccessDraft): boolean {
  if (!draft.modules.has("reservas")) return false;
  const kind = draft.mode === "capacity" ? draft.kind : null;
  return (
    !stored.modules.includes("reservas") ||
    draft.mode !== (stored.reservas?.mode ?? null) ||
    kind !== (stored.reservas?.capacity_kind ?? null)
  );
}

/** El cuerpo del PUT: solo los cuatro módulos de hoy, y Reservas solo si cambia. */
export function accessBody(stored: ClientAccess, draft: AccessDraft, onLive?: "cancel_and_notify"): ClientAccessIn {
  const out: ClientAccessIn = { enabled: draft.enabled, modules: orderedModules(draft.modules) };
  if (reservasDirty(stored, draft) && draft.mode !== null) {
    const kind = draft.mode === "capacity" ? draft.kind : null;
    out.reservas = { mode: draft.mode, ...(kind !== null ? { capacity_kind: kind } : {}), ...(onLive ? { on_live: onLive } : {}) };
  }
  return out;
}

/** ¿Hay algo que guardar? */
export function accessIsDirty(stored: ClientAccess, draft: AccessDraft): boolean {
  const storedModules = ACCESS_MODULES.filter((m) => stored.modules.includes(m));
  return draft.enabled !== stored.enabled || orderedModules(draft.modules).join(",") !== storedModules.join(",") || reservasDirty(stored, draft);
}

const ERRORS = new Set([
  "no_modules",
  "inbox_requires_whatsapp",
  "unknown_module",
  "reservas_mode_required",
  "reservas_kind_required",
  "reservas_kind_forbidden",
  "live_reservations",
  "access_disabled",
  "account_is_partner_member",
  "account_is_other_client",
  "already_member",
  "not_an_invitation",
  "unknown_member",
  "rate_limited",
  "archived",
  "no_partner",
]);

/** La frase de un no de la API: su código, o la genérica. Nunca el texto técnico. */
export function accessErrorKey(code: string | null | undefined): MessageKey {
  return (code && ERRORS.has(code) ? `clientAccess.error.${code}` : "clientAccess.error.generic") as MessageKey;
}
