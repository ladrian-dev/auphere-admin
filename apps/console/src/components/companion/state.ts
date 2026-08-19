/**
 * The Companion timeline reducer (CO-03). Pure — not one React import.
 *
 * This is where the expensive-to-get-wrong logic lives, and it is separate
 * from the components on purpose: CO-04 (the backend half) is being built
 * in parallel, so the only thing that can be verified exhaustively today
 * is this function against the literal payloads of §2 of
 * `docs/companion/CONTRACT-V1.md`.
 *
 * Three rules that are easy to get wrong and each have a test:
 *
 * 1. **Dedupe by `(run_id, seq)`, never by `seq` alone.** §4.3 makes the
 *    timeline belong to the THREAD, so it concatenates several runs — and
 *    `seq` is monotonic *per run*, so two runs of one thread carry
 *    overlapping `seq`. Deduping by `seq` would delete real events of the
 *    second run.
 * 2. **`hitl.resolved` seals the existing card** found by `action_id`; it
 *    never appends a second card (§2.4).
 * 3. **No meter is better than a wrong meter.** If `context.updated` never
 *    arrives (the model is not in `model_profiles`, §2.6) the gauge stays
 *    absent. A bar sitting at 0 % is worse than no bar, because people
 *    believe it.
 *
 * On dedupe and React StrictMode: the cursor is `lastSeq[runId]`, a plain
 * number per run, NOT a mutable `Set`. StrictMode invokes reducers twice;
 * a reducer that mutated a shared `Set` would treat the second invocation
 * as a duplicate and silently drop the event. Numbers copied into a fresh
 * object make the reducer genuinely idempotent.
 */
import {
  type Decision,
  type DiffLine,
  type ImpactItem,
  type IntakeSlot,
  type Phase,
  type PlanStep,
  type Risk,
  type VerifyCheck,
  bool,
  num,
  optNum,
  optStr,
  readChecks,
  readDecision,
  readDiff,
  readImpact,
  readPhase,
  readPlanSteps,
  readPreview,
  readRisk,
  readSlots,
  str,
} from "./types";

export type WireEvent = { seq: number; event: string; data: Record<string, unknown> };

export type ToolItem = {
  kind: "tool";
  id: string;
  runId: string;
  name: string;
  /** Human label from the CO-02 tool catalogue — painted verbatim (§1.4). */
  label: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "failed";
  latencyMs: number | null;
  error: string | null;
  citationId: string | null;
};

export type ActionItem = {
  kind: "action";
  id: string;
  runId: string;
  actionKind: string;
  title: string;
  preview: Record<string, unknown>;
  diff: DiffLine[] | null;
  impact: ImpactItem[];
  expiresAt: string | null;
  /** `pending` until `hitl.resolved` arrives — in the NEXT run (§4.3). */
  state: "pending" | "resolved";
  decision: Decision | null;
  by: string | null;
  at: string | null;
  note: string | null;
};

export type TimelineItem =
  | { kind: "user"; id: string; runId: string; text: string }
  | { kind: "assistant"; id: string; runId: string; text: string }
  | { kind: "thinking"; id: string; runId: string; text: string; startedAt: number; endedAt: number | null }
  | ToolItem
  | { kind: "plan"; id: string; runId: string; steps: PlanStep[]; risk: Risk; reversible: boolean; estimatedTokens: number }
  | { kind: "intake"; id: string; runId: string; slots: IntakeSlot[] }
  | ActionItem
  | { kind: "verify"; id: string; runId: string; actionId: string | null; checks: VerifyCheck[]; ok: boolean }
  | { kind: "notice"; id: string; runId: string; code: NoticeCode; detail: string | null };

/** Closed set: every notice has copy in the i18n lane. */
export type NoticeCode = "gap" | "cancelled" | "error" | "interrupted" | "unsupported";

export type Citation = { id: string; claim: string; source: string; fetchedAt: string | null };

export type CostMeter = { input: number; output: number; model: string | null };
export type ContextMeter = { input: number; max: number; percent: number; compacted: boolean; model: string | null };
export type BudgetMeter = {
  used: number;
  cap: number;
  remaining: number;
  percent: number;
  exhausted: boolean;
  period: string;
  resetsAt: string | null;
};

export type RunStatus = "idle" | "running" | "completed" | "cancelled" | "error" | "interrupted";

export type CompanionState = {
  items: TimelineItem[];
  /** Resume cursor per run — the dedupe key of rule 1. */
  lastSeq: Record<string, number>;
  phase: Phase | null;
  activeRun: string | null;
  runStatus: RunStatus;
  cost: CostMeter | null;
  context: ContextMeter | null;
  budget: BudgetMeter | null;
  citations: Record<string, Citation>;
  /** R1 verdict of the last closed run: it answered without reading. */
  unsupported: boolean;
  error: string | null;
};

export const emptyCompanionState: CompanionState = {
  items: [],
  lastSeq: {},
  phase: null,
  activeRun: null,
  runStatus: "idle",
  cost: null,
  context: null,
  budget: null,
  citations: {},
  unsupported: false,
  error: null,
};

export type CompanionAction =
  | { type: "event"; runId: string; ev: WireEvent; now: number }
  /** The local echo of what the user just sent — it is not an SSE event. */
  | { type: "prompt"; runId: string; text: string; now: number }
  | { type: "run_started"; runId: string }
  | { type: "stream_failed"; runId: string; detail: string; now: number }
  | { type: "reset" };

// ── helpers ────────────────────────────────────────────────────────────

function replace(items: TimelineItem[], index: number, next: TimelineItem): TimelineItem[] {
  const out = items.slice();
  out[index] = next;
  return out;
}

/** Close the open thinking block of this run: any non-reasoning event ends it. */
function closeThinking(items: TimelineItem[], runId: string, now: number): TimelineItem[] {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const it = items[i];
    if (!it || it.runId !== runId) continue;
    if (it.kind !== "thinking") return items;
    if (it.endedAt !== null) return items;
    return replace(items, i, { ...it, endedAt: now });
  }
  return items;
}

function terminal(status: string): RunStatus {
  if (status === "cancelled") return "cancelled";
  if (status === "error" || status === "failed") return "error";
  if (status === "interrupted") return "interrupted";
  return "completed";
}

// ── the reducer ────────────────────────────────────────────────────────

export function companionReducer(state: CompanionState, action: CompanionAction): CompanionState {
  switch (action.type) {
    case "reset":
      return emptyCompanionState;

    case "run_started":
      return { ...state, activeRun: action.runId, runStatus: "running", error: null };

    case "prompt":
      return {
        ...state,
        activeRun: action.runId,
        runStatus: "running",
        error: null,
        unsupported: false,
        items: [...state.items, { kind: "user", id: `u:${action.runId}:${action.now}`, runId: action.runId, text: action.text }],
      };

    case "stream_failed":
      return {
        ...state,
        runStatus: "error",
        error: action.detail,
        items: [
          ...state.items,
          { kind: "notice", id: `n:err:${action.runId}:${action.now}`, runId: action.runId, code: "error", detail: action.detail },
        ],
      };

    case "event":
      return applyEvent(state, action.runId, action.ev, action.now);
  }
}

function applyEvent(state: CompanionState, runId: string, ev: WireEvent, now: number): CompanionState {
  // Rule 1. `seq` is monotonic per run, so the cursor is per run too.
  const seen = state.lastSeq[runId] ?? 0;
  if (ev.seq !== 0 && ev.seq <= seen) return state;
  const lastSeq = ev.seq > seen ? { ...state.lastSeq, [runId]: ev.seq } : state.lastSeq;
  const d = ev.data;
  const base = { ...state, lastSeq };

  switch (ev.event) {
    case "run.started":
      return { ...base, activeRun: runId, runStatus: "running" };

    case "run.completed": {
      const status = terminal(str(d.status, "completed"));
      const err = optStr(d.error);
      const unsupported = bool(d.unsupported);
      let items = closeThinking(base.items, runId, now);
      if (status !== "completed") {
        items = [...items, { kind: "notice", id: `n:${status}:${runId}`, runId, code: status === "cancelled" ? "cancelled" : status === "interrupted" ? "interrupted" : "error", detail: err }];
      } else if (unsupported) {
        items = [...items, { kind: "notice", id: `n:uns:${runId}`, runId, code: "unsupported", detail: null }];
      }
      return { ...base, items, runStatus: status, activeRun: null, error: err, unsupported, phase: status === "completed" ? "done" : base.phase };
    }

    case "resume.gap":
      return {
        ...base,
        items: [
          ...base.items,
          { kind: "notice", id: `n:gap:${runId}:${ev.seq}`, runId, code: "gap", detail: optStr(d.gap_kind) },
        ],
      };

    case "ping":
      return base;

    // §1.4: `label` arrives hardcoded in Spanish and is NOT painted. The
    // phase identifier is, translated by our own i18n lane.
    case "phase.changed": {
      const phase = readPhase(d.phase);
      return phase ? { ...base, phase } : base;
    }

    case "text.delta": {
      const id = `a:${runId}:${str(d.message_id, "0")}`;
      const chunk = str(d.text);
      const items = closeThinking(base.items, runId, now);
      const idx = items.findIndex((i) => i.kind === "assistant" && i.id === id);
      if (idx === -1) return { ...base, items: [...items, { kind: "assistant", id, runId, text: chunk }] };
      const prev = items[idx];
      if (prev?.kind !== "assistant") return { ...base, items };
      return { ...base, items: replace(items, idx, { ...prev, text: prev.text + chunk }) };
    }

    case "reasoning.delta": {
      const id = `r:${runId}:${str(d.message_id, "0")}`;
      const chunk = str(d.text);
      const idx = base.items.findIndex((i) => i.kind === "thinking" && i.id === id);
      if (idx === -1) {
        return { ...base, items: [...base.items, { kind: "thinking", id, runId, text: chunk, startedAt: now, endedAt: null }] };
      }
      const prev = base.items[idx];
      if (prev?.kind !== "thinking") return base;
      return { ...base, items: replace(base.items, idx, { ...prev, text: prev.text + chunk }) };
    }

    case "tool.call.started": {
      const id = str(d.tool_call_id);
      if (!id) return base;
      const items = closeThinking(base.items, runId, now);
      if (items.some((i) => i.kind === "tool" && i.id === id)) return { ...base, items };
      const args = readPreview(d.args);
      return {
        ...base,
        items: [
          ...items,
          { kind: "tool", id, runId, name: str(d.name), label: str(d.label), args, status: "running", latencyMs: null, error: null, citationId: null },
        ],
      };
    }

    case "tool.call.completed": {
      const id = str(d.tool_call_id);
      const idx = base.items.findIndex((i) => i.kind === "tool" && i.id === id);
      if (idx === -1) return base;
      const prev = base.items[idx];
      if (prev?.kind !== "tool") return base;
      return {
        ...base,
        items: replace(base.items, idx, {
          ...prev,
          status: bool(d.ok, true) ? "ok" : "failed",
          latencyMs: optNum(d.latency_ms),
          error: optStr(d.error),
          citationId: optStr(d.citation_id),
        }),
      };
    }

    case "citation": {
      const id = str(d.citation_id);
      if (!id) return base;
      return {
        ...base,
        // `claim` comes from the tool catalogue, not from a customer — one
        // of the two backend strings §1.4 allows us to paint verbatim.
        citations: { ...base.citations, [id]: { id, claim: str(d.claim), source: str(d.source), fetchedAt: optStr(d.fetched_at) } },
      };
    }

    case "cost.updated":
      return { ...base, cost: { input: num(d.input_tokens), output: num(d.output_tokens), model: optStr(d.model) } };

    case "context.updated":
      // Absent event ⇒ absent gauge. See the header note.
      return {
        ...base,
        context: {
          input: num(d.input_tokens),
          max: num(d.max_context),
          percent: num(d.percent),
          compacted: bool(d.compacted),
          model: optStr(d.model),
        },
      };

    case "budget.updated":
      return {
        ...base,
        budget: {
          used: num(d.used),
          cap: num(d.cap),
          remaining: num(d.remaining),
          percent: num(d.percent),
          exhausted: bool(d.exhausted),
          period: str(d.period),
          resetsAt: optStr(d.resets_at),
        },
      };

    // ── CO-04 events. Nothing emits these yet; built against the contract
    //    and doubled in tests. See §1 of PLAN-CO-03.

    case "plan.proposed": {
      const id = str(d.plan_id);
      if (!id) return base;
      const items = closeThinking(base.items, runId, now);
      if (items.some((i) => i.kind === "plan" && i.id === id)) return { ...base, items };
      return {
        ...base,
        items: [
          ...items,
          {
            kind: "plan",
            id,
            runId,
            steps: readPlanSteps(d.steps),
            risk: readRisk(d.risk),
            reversible: bool(d.reversible, true),
            estimatedTokens: num(d.estimated_tokens),
          },
        ],
      };
    }

    case "intake.missing": {
      const slots = readSlots(d.slots);
      if (slots.length === 0) return base;
      const items = closeThinking(base.items, runId, now);
      return { ...base, items: [...items, { kind: "intake", id: `i:${runId}:${ev.seq}`, runId, slots }] };
    }

    case "hitl.requested": {
      const id = str(d.action_id);
      if (!id) return base;
      const items = closeThinking(base.items, runId, now);
      // Deterministic `action_id` (§3.2) + `interrupt()` re-running the
      // node means the same request can legitimately arrive twice.
      if (items.some((i) => i.kind === "action" && i.id === id)) return { ...base, items };
      return {
        ...base,
        items: [
          ...items,
          {
            kind: "action",
            id,
            runId,
            actionKind: str(d.kind),
            title: str(d.title),
            preview: readPreview(d.preview),
            diff: readDiff(d.diff),
            impact: readImpact(d.impact),
            expiresAt: optStr(d.expires_at),
            state: "pending",
            decision: null,
            by: null,
            at: null,
            note: null,
          },
        ],
      };
    }

    // Rule 2: seals the existing card, never appends one. Arrives in the
    // run OPENED BY `resume`, so its `runId` differs from the card's.
    case "hitl.resolved": {
      const id = str(d.action_id);
      const idx = base.items.findIndex((i) => i.kind === "action" && i.id === id);
      if (idx === -1) return base;
      const prev = base.items[idx];
      if (prev?.kind !== "action") return base;
      return {
        ...base,
        items: replace(base.items, idx, {
          ...prev,
          state: "resolved",
          decision: readDecision(d.decision),
          by: optStr(d.by),
          at: optStr(d.at),
          note: optStr(d.note),
        }),
      };
    }

    case "verify.result": {
      const actionId = optStr(d.action_id);
      const items = closeThinking(base.items, runId, now);
      const id = `v:${actionId ?? `${runId}:${ev.seq}`}`;
      if (items.some((i) => i.kind === "verify" && i.id === id)) return { ...base, items };
      return {
        ...base,
        items: [...items, { kind: "verify", id, runId, actionId, checks: readChecks(d.checks), ok: bool(d.ok) }],
      };
    }

    default:
      // An event outside the closed catalogue cannot reach us — the
      // publisher rejects it. Ignoring it keeps a future addition from
      // blanking the drawer.
      return base;
  }
}

// ── selectors ──────────────────────────────────────────────────────────

/** The confirmation blocking the drawer, if any. Expiry is read from
 *  `expires_at` alone (§2.3): the UI never counts 15 minutes itself. */
export function pendingAction(state: CompanionState, now: number): ActionItem | null {
  for (let i = state.items.length - 1; i >= 0; i -= 1) {
    const it = state.items[i];
    if (it?.kind !== "action") continue;
    if (it.state !== "pending") continue;
    if (it.expiresAt && Date.parse(it.expiresAt) <= now) return null;
    return it;
  }
  return null;
}

/** Tool calls made after a thinking block, within the same run — the
 *  "checked 3 things" half of the summary line (§8.2). */
export function thinkingToolCount(state: CompanionState, thinkingId: string): number {
  const start = state.items.findIndex((i) => i.kind === "thinking" && i.id === thinkingId);
  if (start === -1) return 0;
  const runId = state.items[start]?.runId;
  let n = 0;
  for (let i = start + 1; i < state.items.length; i += 1) {
    const it = state.items[i];
    if (!it || it.runId !== runId) break;
    if (it.kind === "tool") n += 1;
  }
  return n;
}

export function isBusy(state: CompanionState): boolean {
  return state.runStatus === "running" && state.activeRun !== null;
}
