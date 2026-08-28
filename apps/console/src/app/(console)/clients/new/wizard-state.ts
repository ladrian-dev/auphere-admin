/**
 * Pure state of the new-client wizard (CP-10): four steps, four run
 * stages with real per-stage status, and the placeholder validation. No
 * React, no fetch — unit-tested in ``__tests__/wizard-state.test.ts``.
 */
import type { SeedPlaceholder } from "@/lib/backend/onboarding";

export const STEPS = ["details", "template", "channel", "review"] as const;
export type StepKey = (typeof STEPS)[number];

export type ChannelChoice = "whatsapp" | "later";
export type StageKey = "create" | "seed" | "publish" | "channel";
export type StageStatus = "pending" | "running" | "done" | "skipped" | "failed";
export type Stage = { key: StageKey; status: StageStatus; error?: string; startedAt?: number; endedAt?: number };

export type WizardValues = {
  name: string;
  external_client_ref: string;
  timezone: string;
  seed_template: string | null;
  placeholders: Record<string, string>;
  channel: ChannelChoice;
  publish_now: boolean;
};

export const initialStages = (): Stage[] => [
  { key: "create", status: "pending" },
  { key: "seed", status: "pending" },
  { key: "publish", status: "pending" },
  { key: "channel", status: "pending" },
];

/** Which stages actually run for these values (seed/publish may be skipped). */
export function planStages(values: Pick<WizardValues, "seed_template" | "publish_now">): Stage[] {
  const stages = initialStages();
  if (!values.seed_template) {
    stages[1]!.status = "skipped";
    stages[2]!.status = "skipped";
  } else if (!values.publish_now) {
    stages[2]!.status = "skipped";
  }
  // The channel stage is informational (connect afterwards) — it completes
  // as soon as the client exists.
  return stages;
}

export type StageEvent =
  | { type: "start"; key: StageKey; at: number }
  | { type: "done"; key: StageKey; at: number }
  | { type: "fail"; key: StageKey; at: number; error: string }
  | { type: "reset"; key: StageKey };

export function stageReducer(stages: Stage[], ev: StageEvent): Stage[] {
  return stages.map((s) => {
    if (s.key !== ev.key) return s;
    switch (ev.type) {
      case "start":
        return { ...s, status: "running", error: undefined, startedAt: ev.at, endedAt: undefined };
      case "done":
        return { ...s, status: "done", error: undefined, endedAt: ev.at };
      case "fail":
        return { ...s, status: "failed", error: ev.error, endedAt: ev.at };
      case "reset":
        return { ...s, status: "pending", error: undefined, startedAt: undefined, endedAt: undefined };
    }
  });
}

/** Overall outcome after a run. */
export function runOutcome(stages: Stage[]): "idle" | "running" | "done" | "partial" {
  if (stages.some((s) => s.status === "running")) return "running";
  if (stages.every((s) => s.status === "pending" || s.status === "skipped")) return "idle";
  if (stages.some((s) => s.status === "failed")) return "partial";
  if (stages.every((s) => s.status === "done" || s.status === "skipped")) return "done";
  return "running";
}

/** The first stage that must run next (pending or failed), in order. */
export function nextStage(stages: Stage[]): StageKey | null {
  const s = stages.find((x) => x.status === "pending" || x.status === "failed");
  return s ? s.key : null;
}

/** Missing required placeholders (trimmed empty counts as missing). */
export function missingPlaceholders(defs: SeedPlaceholder[], values: Record<string, string>): string[] {
  return defs.filter((d) => d.required && !(values[d.key] ?? "").trim()).map((d) => d.key);
}

/** Drop empties so optional blanks fall back to the seed defaults. */
export function cleanPlaceholders(values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(values)) if (v && v.trim()) out[k] = v.trim();
  return out;
}

export function slugify(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

/** Elapsed seconds between the first stage start and the last stage end. */
export function elapsedSeconds(stages: Stage[]): number | null {
  const starts = stages.map((s) => s.startedAt).filter((x): x is number => typeof x === "number");
  const ends = stages.map((s) => s.endedAt).filter((x): x is number => typeof x === "number");
  if (!starts.length || !ends.length) return null;
  return Math.max(0, Math.round((Math.max(...ends) - Math.min(...starts)) / 100) / 10);
}

/** Empty / whitespace-only defaults are clean; any typed field is dirty (QA-04). */
export function wizardIsDirty(values: Pick<WizardValues, "name" | "external_client_ref" | "placeholders">): boolean {
  if (values.name.trim() !== "") return true;
  if (values.external_client_ref.trim() !== "") return true;
  return Object.values(values.placeholders).some((v) => (v ?? "").trim() !== "");
}

/** Dirty + unfinished run → Back / nav / browser back must confirm (QA-04). */
export function wizardShouldBlockLeave(dirty: boolean, outcome: ReturnType<typeof runOutcome>): boolean {
  return dirty && outcome !== "done";
}

/**
 * Seed keys the wizard asks for (describe_placeholders minus tenant.name /
 * tenant.timezone, plus pending policy keys). Used by QA-03 to guarantee
 * every label resolves to a message, never the raw key.
 */
export const SEED_PLACEHOLDER_KEYS = [
  "agent.name",
  "agent.tone",
  "agent.language",
  "owner.first_name",
  "tenant.address",
  "tenant.business_hours_label",
  "tenant.front_desk_phone_label",
  "tenant.instagram_handle",
  "tenant.consultation_price_label",
  "tenant.payment_methods_label",
  "tenant.pricing_table_label",
  "tenant.saturday_label",
  "tenant.surgery_referral_hospital",
  "tenant.surgery_referral_phone",
  "clinical.titular_name",
  "clinical.titular_credential",
  "policies.cancellation.free_hours_before",
  "policies.cancellation.late_fee_pct",
  "policies.no_show.grace_min",
  "policies.no_show.fee_pct",
  "policies.booking.max_advance_days",
  "policies.booking.min_advance_hours",
  "policies.walk_in.max_wait_min",
  "policies.deposit.nail_art_pct",
  "policies.deposit.required_for_party_above",
  "policies.party_size.min",
  "policies.party_size.max",
  "policies.membership.package_validity_days",
  "policies.color.duration_hours_label",
  "policies.minor.consent_required",
  "policies.surgery.deposit_pct",
  "policies.store.currency",
  "policies.store.shipping_info",
  "policies.store.returns_info",
  "policies.wholesale.contact_name",
  "policies.wholesale.contact_phone",
  "policies.admin_access.admin_phones",
  "policies.payment.pago_movil.banco",
  "policies.payment.pago_movil.telefono",
  "policies.payment.pago_movil.cedula",
  "policies.payment.transferencia.banco",
  "policies.payment.transferencia.numero_cuenta",
  "policies.payment.transferencia.titular",
  "policies.payment.transferencia.cedula_rif",
  "policies.payment.binance.pay_id",
] as const;

/** Resolve ``ph.${key}`` via a message table; never return the raw seed key. */
export function resolvePlaceholderLabel(
  key: string,
  table: Record<string, unknown>,
  translate: (phKey: string) => string,
): string {
  const k = `ph.${key}`;
  if (k in table) return translate(k);
  return key.split(".").pop()!.replace(/_/g, " ");
}

export type WizardRefLookup = { found: true } | { found: false; status: number; message: string };

export type WizardRefDecision =
  | { allowNext: true }
  | { allowNext: false; result: { ok: false; status: number; message: string } };

/**
 * Preflight decision for wizard step 1 (QA-02). Existing ref in this
 * partner → 409 stay. Missing (404) → allow next. Other errors stay.
 * Does not fetch.
 */
export function decideWizardRefCheck(lookup: WizardRefLookup, duplicateMessage: string): WizardRefDecision {
  if (lookup.found) {
    return { allowNext: false, result: { ok: false, status: 409, message: duplicateMessage } };
  }
  if (lookup.status === 404) return { allowNext: true };
  return { allowNext: false, result: { ok: false, status: lookup.status, message: lookup.message } };
}

