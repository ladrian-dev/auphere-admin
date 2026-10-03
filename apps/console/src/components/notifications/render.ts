/**
 * Pure rendering helpers for notifications (CP-29): ``kind`` + ``data`` →
 * localized text, severity → tone, seconds → human duration. No React.
 */
import { messages, t as translate, type Locale, type MessageKey } from "@/i18n/messages";
import type { Notification, NotificationSeverity } from "@/lib/backend/onboarding";

export type Tone = "info" | "warning" | "danger";

export function severityTone(sev: NotificationSeverity | string): Tone {
  return sev === "critical" ? "danger" : sev === "warning" ? "warning" : "info";
}

/** Localized one-liner for a notification. Unknown kinds degrade to a generic line. */
export function notificationText(locale: Locale, n: Pick<Notification, "kind" | "data" | "external_client_ref">, clientNames?: Record<string, string>): string {
  const vars: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(n.data ?? {})) {
    if (v == null) continue;
    vars[k] = typeof v === "number" || typeof v === "string" ? v : Array.isArray(v) ? v.join(", ") : JSON.stringify(v);
  }
  // The client's name when the page knows it; the reference is an API
  // identifier and reads like one ("panaderia-la-espiga").
  const ref = n.external_client_ref ?? (typeof vars.external_client_ref === "string" ? vars.external_client_ref : null);
  if (!("client" in vars)) vars.client = (ref && clientNames?.[ref]) ?? ref ?? "—";
  // D8 — una activación que no puede atender no se anuncia como un éxito.
  if (n.kind === "client.activated" && n.data?.can_serve === false) {
    // D8 + A4 — name the missing piece: a channel, quota, or both. Older
    // notifications carry no ``missing`` and keep the quota wording.
    const missing = Array.isArray(n.data?.missing) ? (n.data.missing as unknown[]).map(String) : [];
    const noChannel = missing.includes("whatsapp");
    const noQuota = missing.includes("quota");
    const key: MessageKey =
      noChannel && noQuota
        ? "notif.kind.client.activated.cannot_serve.both"
        : noChannel
          ? "notif.kind.client.activated.cannot_serve.whatsapp"
          : "notif.kind.client.activated.cannot_serve";
    return translate(locale, key, vars);
  }
  if (n.kind === "client.activated" && n.data?.first === true) {
    return `${translate(locale, "notif.kind.client.activated.first")} ${translate(locale, "notif.kind.client.activated", vars)}`;
  }
  const key = `notif.kind.${n.kind}` as MessageKey;
  if (key in messages) return translate(locale, key, vars);
  return translate(locale, "notif.kind.unknown", { kind: n.kind });
}
