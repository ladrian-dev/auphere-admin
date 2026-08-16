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
export function notificationText(locale: Locale, n: Pick<Notification, "kind" | "data" | "external_client_ref">): string {
  const vars: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(n.data ?? {})) {
    if (v == null) continue;
    vars[k] = typeof v === "number" || typeof v === "string" ? v : Array.isArray(v) ? v.join(", ") : JSON.stringify(v);
  }
  if (!("client" in vars)) vars.client = n.external_client_ref ?? (typeof vars.external_client_ref === "string" ? vars.external_client_ref : "—");
  if (n.kind === "client.activated" && n.data?.first === true) {
    return `${translate(locale, "notif.kind.client.activated.first")} ${translate(locale, "notif.kind.client.activated", vars)}`;
  }
  const key = `notif.kind.${n.kind}` as MessageKey;
  if (key in messages) return translate(locale, key, vars);
  return translate(locale, "notif.kind.unknown", { kind: n.kind });
}
