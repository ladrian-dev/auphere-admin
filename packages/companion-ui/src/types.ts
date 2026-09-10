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

/**
 * The 10 phases of §2 of CONTRACT-V2 (was 9 in v1.1 §2.8). Closed enum;
 * the label is ours, never the backend's.
 *
 * The ORDER is the order of §7 of the research, and that is why `publish`
 * sits between `verify` and `respond` rather than being appended: the
 * array is the process, and someone will eventually sort the pill by
 * index. `publish` is the phase of step 8 — the work in progress leads to
 * a publication, step 7 came back green, and the Companion prepares the
 * SECOND confirmation with the diff against the live version in view
 * (rule R5). It is NOT "applying a `kind: publish`", which happens in
 * `execute` like every other write.
 */
export const PHASES = [
  "understand",
  "investigate",
  "intake",
  "plan",
  "awaiting",
  "execute",
  "verify",
  "publish",
  "respond",
  "done",
] as const;
export type Phase = (typeof PHASES)[number];

/**
 * `work_kind` of `intake.missing` — new in v2 §3.1, closed enum of §3.2.
 *
 * It exists so the chip group has a real title ("To create the client I
 * still need…") instead of a generic heading. Without it we would have to
 * infer the kind of work from `key` prefixes, which is guessing.
 *
 * A value outside this enum falls back to the generic title, never to the
 * raw identifier.
 */
export const WORK_KINDS = [
  "create_client",
  "connect_whatsapp",
  "change_prompt",
  "enable_connector",
  "publish",
] as const;
export type WorkKind = (typeof WORK_KINDS)[number];

/** `sla` of `support.ticket` (§4.4). A stable identifier we translate —
 *  the backend never emits the sentence. */
export const SLAS = ["business_hours", "next_business_day", "best_effort"] as const;
export type Sla = (typeof SLAS)[number];

/** `category` of `support.ticket` — mirrors the `kind` (§4.2). */
export const TICKET_CATEGORIES = ["help", "capability"] as const;
export type TicketCategory = (typeof TICKET_CATEGORIES)[number];

/** `warning_key` of a `kind: publish` preview (§7.1). `null` when there is
 *  nothing to warn about. It is a WARNING, never a block. */
export const PUBLISH_WARNINGS = ["not_tried", "trial_failed"] as const;
export type PublishWarning = (typeof PUBLISH_WARNINGS)[number];

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
  // v2 §4.1: the two support tools. They PROPOSE — `console.apply` is
  // still the only `mutates` in the catalogue (guarantee C4, intact).
  "support_help",
  "support_capability",
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

/** The support ticket, as it arrives in `support.ticket` (v2 §4.5). */
export type SupportTicket = {
  /** `AU-142`. The one thing the person will repeat over the phone. */
  ref: string;
  category: TicketCategory;
  /** A stable aggregation SLUG (`connector.shopify`), never prose. */
  topic: string;
  sla: Sla;
};

/**
 * The proposal that precedes the ticket — `hitl.requested.preview` of
 * `kind: support_help | support_capability` (v2 §4.2).
 *
 * `checked` is the list of what the Companion ALREADY read, taken from
 * the tool catalogue's labels. It is what stops the ticket reading as a
 * vague complaint, so it gets its own rendering rather than falling into
 * the generic key/value view.
 */
export type SupportPreview = {
  category: TicketCategory;
  topic: string;
  clientRef: string | null;
  need: string;
  checked: string[];
  alternative: string | null;
  /** §25.4: a bridge does NOT replace the ticket. Labelled, always. */
  bridge: boolean;
};

/** One assertion of one trial turn (v2 §7). `name` is a stable English
 *  identifier we translate; `expected`/`actual` are always strings. */
export type TrialCheck = { name: string; expected: string; actual: string; ok: boolean };

export type TrialTurn = {
  index: number;
  /** Written by the COMPANION, like `citation.claim` — safe to paint. */
  probe: string;
  ok: boolean;
  latencyMs: number | null;
  checks: TrialCheck[];
};

/**
 * `verify.result.trial` (v2 §7).
 *
 * **`ran: false` is not the same as no trial at all.** `trial: null` on
 * the wire means "this action does not admit a trial" (an `invite`, a
 * `usage_alerts`) and paints nothing; `{"ran": false}` means "it does
 * admit one and it was not done", which is exactly the thing publishing
 * warns about. `readTrial` keeps them apart — see `Trial | null`.
 *
 * It NEVER carries the draft agent's reply, not whole, not trimmed, not
 * summarised. Whoever wants to read the conversation opens the playground
 * thread by `threadId`.
 */
export type Trial = {
  ran: boolean;
  threadId: string | null;
  ok: boolean | null;
  tokens: number | null;
  turns: TrialTurn[];
};

/** The publish warning of a `kind: publish` preview (v2 §7.1). */
export type PublishNotice = { trialRan: boolean; trialOk: boolean | null; warning: PublishWarning | null };

/** `budget.paused` (v2 §6.4) and the body of the 409 `budget_paused`. */
export type BudgetPause = {
  used: number;
  cap: number;
  period: string;
  resetsAt: string | null;
  /** `partner` is the only value today; the enum stays open. Read, not
   *  painted: with a single value, saying it is noise. */
  scope: string;
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

/** A `work_kind` outside the closed enum of §3.2 reads as `null`, and the
 *  card falls back to its generic title — never to the identifier. */
export function readWorkKind(v: unknown): WorkKind | null {
  return typeof v === "string" && (WORK_KINDS as readonly string[]).includes(v) ? (v as WorkKind) : null;
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

/**
 * `verify.result.trial` (v2 §7). Returns `null` ONLY for a wire `null` or
 * a non-object — "this action does not admit a trial". A `{"ran": false}`
 * comes back as an object so the caller can paint the "not tried" notice,
 * which is the whole point of the distinction.
 */
export function readTrial(v: unknown): Trial | null {
  if (!isRecord(v)) return null;
  return {
    ran: bool(v.ran),
    threadId: optStr(v.thread_id),
    ok: typeof v.ok === "boolean" ? v.ok : null,
    tokens: optNum(v.tokens),
    turns: readTrialTurns(v.turns),
  };
}

function readTrialTurns(v: unknown): TrialTurn[] {
  return list(v)
    .filter(isRecord)
    .map((turn, i) => ({
      index: num(turn.index, i + 1),
      probe: str(turn.probe),
      ok: bool(turn.ok),
      latencyMs: optNum(turn.latency_ms),
      checks: readTrialChecks(turn.checks),
    }));
}

function readTrialChecks(v: unknown): TrialCheck[] {
  return list(v)
    .filter(isRecord)
    .map((c) => ({
      name: str(c.name),
      // "always strings" (§7) — coerced anyway so a regressed backend
      // still renders instead of blanking the cell.
      expected: typeof c.expected === "number" ? String(c.expected) : str(c.expected),
      actual: typeof c.actual === "number" ? String(c.actual) : str(c.actual),
      ok: bool(c.ok),
    }));
}

/** `support.ticket` (v2 §4.5). A ticket without a `ref` is not a ticket:
 *  the identifier is the entire reason the event exists. */
export function readTicket(v: unknown): SupportTicket | null {
  if (!isRecord(v)) return null;
  const ref = str(v.ticket_ref);
  if (!ref) return null;
  return {
    ref,
    category: oneOf(v.category, TICKET_CATEGORIES, "help"),
    topic: str(v.topic),
    sla: oneOf(v.sla, SLAS, "best_effort"),
  };
}

/**
 * The support proposal inside `hitl.requested.preview` (v2 §4.2).
 *
 * Called only for the two support `kind`s. `preview` is a free object, so
 * every field is narrowed rather than asserted — an absent `checked` gives
 * an empty list and the rest of the ticket still renders.
 */
export function readSupportPreview(v: unknown): SupportPreview | null {
  if (!isRecord(v)) return null;
  return {
    category: oneOf(v.category, TICKET_CATEGORIES, "help"),
    topic: str(v.topic),
    clientRef: optStr(v.client_ref),
    need: str(v.need),
    checked: list(v.checked).filter((c): c is string => typeof c === "string" && c.length > 0),
    alternative: optStr(v.alternative),
    bridge: bool(v.bridge),
  };
}

/**
 * The trial warning inside a `kind: publish` preview (v2 §7.1).
 *
 * Returns `null` when the preview says nothing about a trial — an older
 * CO-04 payload, for instance. It is a warning and never a block: the user
 * can publish without trying, and prohibiting it would turn the trial into
 * a toll people learn to route around.
 */
export function readPublishNotice(v: unknown): PublishNotice | null {
  if (!isRecord(v)) return null;
  if (!("trial_ran" in v) && !("warning_key" in v)) return null;
  const warning =
    typeof v.warning_key === "string" && (PUBLISH_WARNINGS as readonly string[]).includes(v.warning_key)
      ? (v.warning_key as PublishWarning)
      : null;
  return {
    trialRan: bool(v.trial_ran),
    trialOk: typeof v.trial_ok === "boolean" ? v.trial_ok : null,
    warning,
  };
}

/** `budget.paused` (v2 §6.4), and the 409 body, which carries the same
 *  snapshot precisely so the UI needs no second request. */
export function readBudgetPause(v: unknown): BudgetPause | null {
  if (!isRecord(v)) return null;
  return {
    used: num(v.used),
    cap: num(v.cap),
    period: str(v.period),
    resetsAt: optStr(v.resets_at),
    scope: str(v.scope, "partner"),
  };
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
