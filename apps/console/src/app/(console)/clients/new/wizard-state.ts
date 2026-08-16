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
