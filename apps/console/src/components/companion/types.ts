/**
 * Narrowing of the Companion event payloads (CO-03).
 *
 * The wire type is `{seq, event, data}` with `data` deliberately untyped:
 * the payload shape depends on `event` and the API publishes against a
 * **closed catalogue** (`api/companion_streaming.py::COMPANION_EVENTS`)
 * that guarantees which keys may appear. These readers are the other half
 * of that contract — they turn `Record<string, unknown>` into something
 * typed **by checking**, never by asserting.
 *
 * Every key here is literal from §2 of `docs/companion/CONTRACT-V1.md`. A
 * key the contract does not declare never reaches the browser: the
 * publisher drops it silently. So a reader that guesses a name renders
 * nothing and fails quietly — which is why these are tested against
 * fixtures carrying the contract's literal payloads.
 *
 * Five of these events (`plan.proposed`, `intake.missing`, `hitl.*`,
 * `verify.result`) are not emitted by anything yet — CO-04 builds them in
 * parallel. They are written against the contract and doubled in tests.
 */

/** The 9 phases of §2.8. Closed enum; the label is ours, never the backend's. */
export const PHASES = [
  "understand",
  "investigate",
  "intake",
  "plan",
  "awaiting",
  "execute",
  "verify",
  "respond",
  "done",
] as const;
export type Phase = (typeof PHASES)[number];

export const RISKS = ["low", "medium", "high"] as const;
export type Risk = (typeof RISKS)[number];

export const DECISIONS = ["confirm", "edit", "cancel"] as const;
export type Decision = (typeof DECISIONS)[number];

/** `kind` of §3.1. Open on purpose at the type level: §3.4 requires the UI
 *  to fall back to a generic view for a kind it does not know, so that
 *  CO-04 can add one without breaking CO-03. */
export const ACTION_KINDS = [
  "client",
  "prompt",
  "policy",
  "tools",
  "skills",
  "publish",
  "channel_role",
  "usage_alerts",
  "invite",
] as const;
export type ActionKind = (typeof ACTION_KINDS)[number];

export type PlanStep = {
  index: number;
  kind: string;
  tool: string;
  /** Written by the model. Painted verbatim and NOT translated (§2.1). */
  title: string;
  client_ref: string | null;
  reversible: boolean;
};

export type IntakeSlot = {
  key: string;
  label: string;
  why: string;
  examples: string[];
  required: boolean;
};

export type DiffLine = { op: "add" | "del" | "ctx"; line: number; before?: string; after?: string };
export type ImpactItem = { key: string; value: string; severity: "info" | "warn" | "danger" };
export type VerifyCheck = {
  /** Stable English identifier — translated by our i18n lane (§2.5). */
  name: string;
  expected: string;
  actual: string;
  ok: boolean;
};

// ── primitive readers ──────────────────────────────────────────────────
//
// `unknown` in, narrow out. `num`/`str` return a fallback rather than
// throwing: one malformed field must not blank the whole drawer.

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
export function optStr(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}
export function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}
export function optNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
export function bool(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function list(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function oneOf<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

export function readPhase(v: unknown): Phase | null {
  return typeof v === "string" && (PHASES as readonly string[]).includes(v) ? (v as Phase) : null;
}

export function readPlanSteps(v: unknown): PlanStep[] {
  return list(v)
    .filter(isRecord)
    .map((s, i) => ({
      index: num(s.index, i + 1),
      kind: str(s.kind),
      tool: str(s.tool),
      title: str(s.title),
      client_ref: optStr(s.client_ref),
      reversible: bool(s.reversible, true),
    }));
}

export function readSlots(v: unknown): IntakeSlot[] {
  return list(v)
    .filter(isRecord)
    .map((s) => ({
      key: str(s.key),
      label: str(s.label),
      why: str(s.why),
      // "always a list (possibly empty), never null" — §2.2.
      examples: list(s.examples).filter((e): e is string => typeof e === "string"),
      required: bool(s.required, true),
    }))
    .filter((s) => s.key !== "");
}

export function readDiff(v: unknown): DiffLine[] | null {
  if (!Array.isArray(v)) return null;
  return v.filter(isRecord).map((d) => ({
    op: oneOf(d.op, ["add", "del", "ctx"] as const, "ctx"),
    line: num(d.line),
    before: typeof d.before === "string" ? d.before : undefined,
    after: typeof d.after === "string" ? d.after : undefined,
  }));
}

export function readImpact(v: unknown): ImpactItem[] {
  return list(v)
    .filter(isRecord)
    .map((i) => ({
      key: str(i.key),
      value: str(i.value),
      severity: oneOf(i.severity, ["info", "warn", "danger"] as const, "info"),
    }));
}

export function readChecks(v: unknown): VerifyCheck[] {
  return list(v)
    .filter(isRecord)
    .map((c) => ({
      name: str(c.name),
      // "always strings, even for numbers" (§2.5) — but a backend that
      // regresses to a raw number must still render, so coerce.
      expected: typeof c.expected === "number" ? String(c.expected) : str(c.expected),
      actual: typeof c.actual === "number" ? String(c.actual) : str(c.actual),
      ok: bool(c.ok),
    }));
}

export function readRisk(v: unknown): Risk {
  return oneOf(v, RISKS, "low");
}
export function readDecision(v: unknown): Decision {
  return oneOf(v, DECISIONS, "confirm");
}

/** `preview` is a free object (§3.4): passed through untouched, rendered
 *  by kind with a generic key/value fallback. */
export function readPreview(v: unknown): Record<string, unknown> {
  return isRecord(v) ? v : {};
}
