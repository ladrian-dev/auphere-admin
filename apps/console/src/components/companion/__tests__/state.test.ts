import { describe, expect, it } from "vitest";

import {
  type CompanionState,
  companionReducer,
  emptyCompanionState,
  isBusy,
  pendingAction,
  thinkingToolCount,
} from "../state";
import * as f from "./fixtures";

/**
 * The reducer against the frozen contract. Nothing emits the CO-04 events
 * yet, so these fixtures ARE the integration test until Phase 2.
 */
function apply(state: CompanionState, runId: string, events: ReturnType<typeof f.ev>[], now = 1_000): CompanionState {
  return events.reduce((s, ev) => companionReducer(s, { type: "event", runId, ev, now }), state);
}

describe("companionReducer — dedupe", () => {
  it("drops a repeated (run_id, seq) but keeps the same seq from ANOTHER run", () => {
    // The trap of §4.3: the timeline is of the THREAD, and `seq` is
    // monotonic PER RUN, so run A and run B carry overlapping seqs.
    // Deduping by seq alone would delete run B's real events.
    let s = apply(emptyCompanionState, "run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "hola de A")]);
    s = apply(s, "run-a", [f.textDelta(2, "REPETIDO")]);
    expect(s.items.filter((i) => i.kind === "assistant")).toHaveLength(1);
    expect(s.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "hola de A" });

    s = apply(s, "run-b", [f.runStarted(1, "run-b"), f.textDelta(2, "hola de B")]);
    const assistants = s.items.filter((i) => i.kind === "assistant");
    expect(assistants).toHaveLength(2);
    expect(assistants[1]).toMatchObject({ text: "hola de B" });
  });

  it("is idempotent when the same action is applied twice (React StrictMode)", () => {
    // StrictMode invokes reducers twice. A reducer that mutated a shared
    // Set would treat the second call as a duplicate and drop the event.
    const action = { type: "event", runId: "run-a", ev: f.textDelta(1, "x"), now: 1 } as const;
    const once = companionReducer(emptyCompanionState, action);
    const twice = companionReducer(emptyCompanionState, action);
    expect(twice.items).toEqual(once.items);
    expect(twice.lastSeq).toEqual(once.lastSeq);
  });

  it("merges REST history and the live stream without duplicating", () => {
    // The C1 pattern: history 1..3 then a stream opened at 0 replaying 1..5.
    let s = apply(emptyCompanionState, "run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "ho"), f.textDelta(3, "la")]);
    s = apply(s, "run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "ho"), f.textDelta(3, "la"), f.textDelta(4, "!"), f.runCompleted(5, "run-a")]);
    expect(s.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "hola!" });
    expect(s.runStatus).toBe("completed");
  });
});

describe("companionReducer — phase", () => {
  it("keeps the phase identifier and never the backend's hardcoded label", () => {
    const s = apply(emptyCompanionState, "r", [f.phase(1, "investigate")]);
    expect(s.phase).toBe("investigate");
    expect(JSON.stringify(s)).not.toContain("ETIQUETA DEL BACKEND");
  });

  it("ignores a phase outside the closed enum of §2.8", () => {
    const s = apply(emptyCompanionState, "r", [f.phase(1, "investigate"), f.phase(2, "teleporting")]);
    expect(s.phase).toBe("investigate");
  });
});

describe("companionReducer — meters", () => {
  it("leaves the context gauge ABSENT when the event never arrives (§2.6)", () => {
    // A bar at 0 % is worse than no bar: people believe a bar.
    const s = apply(emptyCompanionState, "r", [f.runStarted(1, "r"), f.costUpdated(2)]);
    expect(s.context).toBeNull();
    expect(s.cost).toMatchObject({ input: 12000, output: 800 });
  });

  it("reads the percent from the backend, never recomputing it", () => {
    const s = apply(emptyCompanionState, "r", [f.contextUpdated(1, 47)]);
    expect(s.context?.percent).toBe(47);
    expect(s.context?.compacted).toBe(false);
  });

  it("tracks the monthly cap", () => {
    const s = apply(emptyCompanionState, "r", [f.budgetUpdated(1, true)]);
    expect(s.budget).toMatchObject({ used: 310000, cap: 500000, exhausted: true, period: "2026-08" });
  });
});

describe("companionReducer — tools and citations", () => {
  it("completes a tool card in place and attaches its citation", () => {
    const s = apply(emptyCompanionState, "r", [
      f.toolStarted(1, "t1"),
      f.citation(2, "c1"),
      f.toolCompleted(3, "t1", true, "c1"),
    ]);
    const tools = s.items.filter((i) => i.kind === "tool");
    expect(tools).toHaveLength(1);
    expect(tools[0]).toMatchObject({ status: "ok", latencyMs: 240, citationId: "c1" });
    expect(s.citations.c1).toMatchObject({ claim: "Consumo del partner (client_ref=boreal)" });
  });

  it("marks a failed tool without dropping the card", () => {
    const s = apply(emptyCompanionState, "r", [f.toolStarted(1, "t1"), f.toolCompleted(2, "t1", false)]);
    expect(s.items.find((i) => i.kind === "tool")).toMatchObject({ status: "failed", error: "upstream 500" });
  });
});

describe("companionReducer — thinking", () => {
  it("closes the thinking block when a non-reasoning event arrives and counts the tools after it", () => {
    let s = companionReducer(emptyCompanionState, { type: "event", runId: "r", ev: f.reasoningDelta(1, "pensando"), now: 1_000 });
    s = companionReducer(s, { type: "event", runId: "r", ev: f.toolStarted(2, "t1"), now: 5_000 });
    s = companionReducer(s, { type: "event", runId: "r", ev: f.toolStarted(3, "t2"), now: 6_000 });
    const thinking = s.items.find((i) => i.kind === "thinking");
    expect(thinking).toMatchObject({ startedAt: 1_000, endedAt: 5_000 });
    expect(thinkingToolCount(s, thinking!.id)).toBe(2);
  });
});

describe("companionReducer — the CO-04 events", () => {
  it("renders a plan without treating it as a commitment", () => {
    const s = apply(emptyCompanionState, "r", [f.planProposed(1)]);
    const plan = s.items.find((i) => i.kind === "plan");
    expect(plan).toMatchObject({ id: "3f2a", risk: "low", reversible: true, estimatedTokens: 18000 });
    expect(plan && plan.kind === "plan" && plan.steps[0]).toMatchObject({
      index: 1,
      title: "Ajustar el prompt de Clínica Boreal",
      client_ref: "boreal",
    });
    // A plan alone must never block the composer.
    expect(pendingAction(s, Date.now())).toBeNull();
  });

  it("reads the intake slots, keeping examples a list", () => {
    const s = apply(emptyCompanionState, "r", [f.intakeMissing(1)]);
    const intake = s.items.find((i) => i.kind === "intake");
    expect(intake && intake.kind === "intake" && intake.slots[0]).toMatchObject({
      key: "forbidden_behaviour",
      required: true,
      examples: ["No dar precios por WhatsApp", "No agendar sin seña"],
    });
  });

  it("SEALS the request card on hitl.resolved instead of appending a second one — across runs", () => {
    // §4.3: `hitl.resolved` arrives in the NEW run opened by `resume`.
    let s = apply(emptyCompanionState, "run-a", [f.hitlRequested(1)]);
    s = apply(s, "run-b", [f.hitlResolved(1, "9c1e", "edit")]);
    const actions = s.items.filter((i) => i.kind === "action");
    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({
      state: "resolved",
      decision: "edit",
      by: "user_a_ab12cd34",
      note: "Mejor sin tocar el horario.",
    });
  });

  it("does not duplicate the card when interrupt() re-runs the node (§3.2)", () => {
    const s = apply(emptyCompanionState, "run-a", [f.hitlRequested(1), f.hitlRequested(2)]);
    expect(s.items.filter((i) => i.kind === "action")).toHaveLength(1);
  });

  it("keeps the verification result and its per-check outcome", () => {
    const s = apply(emptyCompanionState, "r", [f.verifyResult(1, "9c1e", false)]);
    const verify = s.items.find((i) => i.kind === "verify");
    expect(verify).toMatchObject({ actionId: "9c1e", ok: false });
    expect(verify && verify.kind === "verify" && verify.checks).toEqual([
      { name: "active_version", expected: "8", actual: "8", ok: true },
      { name: "tools_enabled", expected: "3", actual: "2", ok: false },
    ]);
  });
});

describe("pendingAction — expiry comes only from expires_at (§2.3)", () => {
  it("returns the card while the deadline holds", () => {
    const s = apply(emptyCompanionState, "r", [f.hitlRequested(1, "9c1e", "2126-01-01T00:00:00Z")]);
    expect(pendingAction(s, Date.parse("2026-08-18T14:20:00Z"))?.id).toBe("9c1e");
  });

  it("returns null once expires_at has passed — the UI never counts 15 minutes itself", () => {
    const s = apply(emptyCompanionState, "r", [f.hitlRequested(1, "9c1e", "2026-08-18T14:33:00Z")]);
    expect(pendingAction(s, Date.parse("2026-08-18T14:34:00Z"))).toBeNull();
  });

  it("returns null once resolved", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlRequested(1)]);
    s = apply(s, "run-b", [f.hitlResolved(1)]);
    expect(pendingAction(s, Date.now())).toBeNull();
  });
});

describe("companionReducer — run lifecycle", () => {
  it("adds a notice and clears the active run when a run is cancelled", () => {
    let s = apply(emptyCompanionState, "r", [f.runStarted(1, "r")]);
    expect(isBusy(s)).toBe(true);
    s = apply(s, "r", [f.runCompleted(2, "r", "cancelled")]);
    expect(s.runStatus).toBe("cancelled");
    expect(s.activeRun).toBeNull();
    expect(s.items.find((i) => i.kind === "notice")).toMatchObject({ code: "cancelled" });
  });

  it("surfaces the R1 unsupported verdict as a notice", () => {
    const s = apply(emptyCompanionState, "r", [f.runStarted(1, "r"), f.runCompleted(2, "r", "completed", true)]);
    expect(s.unsupported).toBe(true);
    expect(s.items.find((i) => i.kind === "notice")).toMatchObject({ code: "unsupported" });
  });

  it("turns resume.gap into a visible notice rather than a dead end", () => {
    const s = apply(emptyCompanionState, "r", [f.resumeGap(1)]);
    expect(s.items.find((i) => i.kind === "notice")).toMatchObject({ code: "gap" });
  });

  it("ignores an event outside the closed catalogue instead of blanking", () => {
    const s = apply(emptyCompanionState, "r", [f.textDelta(1, "ok"), f.ev(2, "future.event", { whatever: 1 })]);
    expect(s.items.filter((i) => i.kind === "assistant")).toHaveLength(1);
  });

  it("records the local echo of the user's prompt", () => {
    const s = companionReducer(emptyCompanionState, { type: "prompt", runId: "r", text: "hola", now: 1 });
    expect(s.items[0]).toMatchObject({ kind: "user", text: "hola" });
    expect(s.runStatus).toBe("running");
  });
});
