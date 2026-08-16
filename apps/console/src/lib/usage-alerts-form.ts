/** Pure parser of the usage-alerts form (CP-24) — unit-tested. */
import type { UsageAlertsInput } from "./backend/home-usage";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type ParsedAlerts = { ok: true; value: UsageAlertsInput } | { ok: false; error: "cap" | "email"; email?: string };

export function parseAlertsForm(input: { cap: string; recipients: string; enabled: boolean }): ParsedAlerts {
  const capText = input.cap.trim().replace(/[.\s]/g, "");
  let cap: number | null = null;
  if (capText !== "") {
    if (!/^\d+$/.test(capText)) return { ok: false, error: "cap" };
    cap = Number(capText);
    if (!Number.isSafeInteger(cap) || cap < 0) return { ok: false, error: "cap" };
  }
  const recipients = [...new Set(input.recipients.split(/[\n,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean))];
  for (const r of recipients) if (!EMAIL.test(r)) return { ok: false, error: "email", email: r };
  return { ok: true, value: { cap_messages_month: cap, recipients, enabled: input.enabled } };
}
