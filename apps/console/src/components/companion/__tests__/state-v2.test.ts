import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";

import { type CompanionState, companionReducer, emptyCompanionState, trialClientRef } from "../state";
import { PHASES, readBudgetPause, readPublishNotice, readSupportPreview, readTrial } from "../types";
import * as f from "./fixtures";

/**
 * The reducer and the readers against **CONTRACT-V2**.
 *
 * Nothing emits any of this yet — CO-06 and CO-08 are being built in
 * parallel in worktrees this one cannot see — so these fixtures ARE the
 * integration test until Phase 2. Every key is literal from the contract,
 * because the publisher silently drops any key the catalogue does not
 * declare: a misspelt name would fail quietly in production instead of
 * loudly here.
 */
function apply(state: CompanionState, runId: string, events: ReturnType<typeof f.ev>[], now = 1_000): CompanionState {
  return events.reduce((s, ev) => companionReducer(s, { type: "event", runId, ev, now }), state);
}

// ── §2 · the phase enum ────────────────────────────────────────────────

describe("phases — `publish` (v2 §2)", () => {
  it("has ten values, with `publish` between `verify` and `respond`", () => {
    expect(PHASES).toHaveLength(10);
    // The order is the process of §7, not an arbitrary list.
    expect(PHASES.indexOf("publish")).toBe(PHASES.indexOf("verify") + 1);
    expect(PHASES.indexOf("respond")).toBe(PHASES.indexOf("publish") + 1);
  });

  it("accepts `publish` and still ignores the backend's Spanish label", () => {
    const s = apply(emptyCompanionState, "run-a", [f.phase(1, "publish")]);
    expect(s.phase).toBe("publish");
    // §1.4: `label` arrives hardcoded in Spanish and is never painted. The
    // fixture ships "ETIQUETA DEL BACKEND" precisely so this can be shown.
    expect(JSON.stringify(s)).not.toContain("ETIQUETA DEL BACKEND");
  });

  it("ignores a phase outside the closed enum instead of blanking the pill", () => {
    let s = apply(emptyCompanionState, "run-a", [f.phase(1, "verify")]);
    s = apply(s, "run-a", [f.phase(2, "teleporting")]);
    expect(s.phase).toBe("verify");
  });
});

// ── §17 (v2.1) · tool names keep the dot on this side ──────────────────

describe("tool names — the interface sees the CATALOGUE name, never the wire one", () => {
  /**
   * v2.1 §17: Anthropic rejects `.` in `tools[].name`, so the engine
   * translates `.` → `__` **at the provider boundary only**. The catalogue
   * is not renamed, and `tool.call.started.name` still arrives here with
   * the dot.
   *
   * This guards the direction that would fail silently: a double
   * underscore creeping into our copy or our doubles would key off a name
   * that never arrives, and the tool card would quietly fall back to the
   * backend `label` — no error, just worse wording nobody traces back.
   */
  it("has no wire-form tool name in the i18n lane", () => {
    const toolKeys = Object.keys(messages).filter((k) => k.startsWith("companion.tool.name."));
    expect(toolKeys.length).toBeGreaterThan(18);
    for (const key of toolKeys) {
      expect(key, `${key} carries the provider wire form`).not.toContain("__");
      // …and every one is `companion.tool.name.<namespace>.<tool>`.
      expect(key.slice("companion.tool.name.".length)).toMatch(/^[a-z_]+\.[a-z_]+$/);
    }
  });

  it("has no wire-form tool name in the contract fixtures", () => {
    const wire = JSON.stringify([
      f.toolStarted(1, "tc-1"),
      f.toolCompleted(2, "tc-1"),
      f.planProposed(3),
      f.hitlSupportRequested(4),
    ]);
    expect(wire).not.toContain("__");
    expect(wire).toContain("console.get_usage");
  });
});

// ── §3 · intake with `work_kind` ───────────────────────────────────────

describe("intake.missing — `work_kind` (v2 §3)", () => {
  it("carries the work kind through to the timeline item", () => {
    const s = apply(emptyCompanionState, "run-a", [f.intakeMissing(1, "connect_whatsapp")]);
    const item = s.items.find((i) => i.kind === "intake");
    expect(item).toMatchObject({ workKind: "connect_whatsapp" });
  });

  it("reads a work kind outside the closed enum as null, never as the identifier", () => {
    const s = apply(emptyCompanionState, "run-a", [f.intakeMissing(1, "teleport_client")]);
    expect(s.items.find((i) => i.kind === "intake")).toMatchObject({ workKind: null });
  });

  it("reads an absent work kind as null — an older CO-04 payload still renders", () => {
    const s = apply(emptyCompanionState, "run-a", [f.intakeMissing(1, null)]);
    expect(s.items.find((i) => i.kind === "intake")).toMatchObject({ workKind: null });
  });

  it("EMPTY: no slots means no card at all, not an empty card", () => {
    const s = apply(emptyCompanionState, "run-a", [f.ev(1, "intake.missing", { slots: [], work_kind: "publish" })]);
    expect(s.items.filter((i) => i.kind === "intake")).toHaveLength(0);
  });
});

// ── §4 · the support ticket ────────────────────────────────────────────

describe("support.ticket — seals the card (v2 §4.5)", () => {
  it("attaches to the `hitl.requested` card by `action_id`, adding no loose card", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlSupportRequested(1, "act-1")]);
    const before = s.items.length;
    s = apply(s, "run-a", [f.supportTicket(2, "act-1", "AU-142")]);
    expect(s.items).toHaveLength(before);
    const card = s.items.find((i) => i.kind === "action");
    expect(card).toMatchObject({
      ticket: { ref: "AU-142", category: "help", topic: "connector.shopify", sla: "business_hours" },
    });
  });

  it("drops a ticket whose action is not in the timeline instead of orphaning it", () => {
    const s = apply(emptyCompanionState, "run-a", [f.supportTicket(1, "unknown-action")]);
    expect(s.items).toHaveLength(0);
  });

  it("drops a ticket with no reference: the identifier IS the reason the event exists", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlSupportRequested(1, "act-1")]);
    s = apply(s, "run-a", [f.supportTicket(2, "act-1", "")]);
    expect(s.items.find((i) => i.kind === "action")).toMatchObject({ ticket: null });
  });

  it("falls back to safe values for an sla or category outside the enum", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlSupportRequested(1, "act-1")]);
    s = apply(s, "run-a", [f.supportTicket(2, "act-1", "AU-9", "urgent", "immediately")]);
    const card = s.items.find((i) => i.kind === "action");
    // `best_effort` is the honest fallback: never promise a tighter SLA
    // than the one we can read.
    expect(card).toMatchObject({ ticket: { sla: "best_effort", category: "help" } });
  });
});

describe("readSupportPreview (v2 §4.2)", () => {
  it("reads the literal preview of the contract", () => {
    const ev = f.hitlSupportRequested(1, "act-1", "support_capability", true);
    const preview = readSupportPreview(ev.data.preview);
    expect(preview).toMatchObject({
      category: "capability",
      topic: "connector.shopify",
      clientRef: "boreal",
      bridge: true,
    });
    expect(preview?.checked).toHaveLength(3);
  });

  it("PARTIAL: an absent `checked` gives an empty list and the rest still reads", () => {
    const preview = readSupportPreview({ category: "help", topic: "quota.clients", need: "Más cupo" });
    expect(preview).toMatchObject({ checked: [], alternative: null, bridge: false, need: "Más cupo" });
  });
});

// ── §7 · the trial ─────────────────────────────────────────────────────

describe("verify.result.trial — null is NOT {ran:false} (v2 §7)", () => {
  it("reads a wire null as null: this action admits no trial", () => {
    const s = apply(emptyCompanionState, "run-a", [f.verifyResult(1, "act-1", true, null)]);
    expect(s.items.find((i) => i.kind === "verify")).toMatchObject({ trial: null });
  });

  it("reads {ran:false} as an object: it admits one and none was run", () => {
    const s = apply(emptyCompanionState, "run-a", [f.verifyResult(1, "act-1", true, f.trialNotRun())]);
    const item = s.items.find((i) => i.kind === "verify");
    expect(item?.kind === "verify" && item.trial).not.toBeNull();
    expect(item).toMatchObject({ trial: { ran: false } });
  });

  it("reads a full trial with its turns and named assertions", () => {
    const s = apply(emptyCompanionState, "run-a", [f.verifyResult(1, "act-1", true, f.trialRan(true))]);
    const item = s.items.find((i) => i.kind === "verify");
    expect(item).toMatchObject({
      trial: {
        ran: true,
        threadId: "4d2b",
        ok: true,
        tokens: 4210,
        turns: [{ index: 1, probe: "¿Cuánto cuesta el bótox?", ok: true, latencyMs: 1840 }],
      },
    });
  });

  it("never carries the draft agent's reply — the shape has nowhere to put one", () => {
    const trial = readTrial(f.trialRan(true));
    const keys = Object.keys(trial ?? {});
    for (const forbidden of ["reply", "answer", "text", "content", "message", "transcript"]) {
      expect(keys).not.toContain(forbidden);
    }
    for (const turn of trial?.turns ?? []) {
      expect(Object.keys(turn).sort()).toEqual(["checks", "index", "latencyMs", "ok", "probe"]);
    }
  });

  it("coerces a numeric expected/actual so a regressed backend still renders", () => {
    const trial = readTrial({
      ran: true,
      turns: [{ index: 1, probe: "p", ok: true, checks: [{ name: "n", expected: 8, actual: 8, ok: true }] }],
    });
    expect(trial?.turns[0]?.checks[0]).toMatchObject({ expected: "8", actual: "8" });
  });
});

describe("trialClientRef — the link the contract cannot build alone", () => {
  it("recovers the client from the action card, since `verify.result` has none", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlSupportRequested(1, "act-1")]);
    s = apply(s, "run-a", [f.verifyResult(2, "act-1", true, f.trialRan())]);
    expect(trialClientRef(s, "act-1")).toBe("boreal");
  });

  it("returns null rather than guess when the preview carries no client", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlPublishRequested(1, "act-2", null)]);
    s = apply(s, "run-a", [f.verifyResult(2, "act-9", true, f.trialRan())]);
    // Unknown action id: no correlation, so no link. A dead link would be
    // worse than none.
    expect(trialClientRef(s, "act-9")).toBeNull();
    expect(trialClientRef(s, null)).toBeNull();
  });
});

// ── §7.1 · publishing without a trial ──────────────────────────────────

describe("readPublishNotice (v2 §7.1)", () => {
  it("reads `not_tried`", () => {
    const ev = f.hitlPublishRequested(1, "act-1", "not_tried");
    expect(readPublishNotice(ev.data.preview)).toMatchObject({ trialRan: false, trialOk: null, warning: "not_tried" });
  });

  it("reads `trial_failed`", () => {
    const ev = f.hitlPublishRequested(1, "act-1", "trial_failed");
    expect(readPublishNotice(ev.data.preview)).toMatchObject({ trialRan: true, trialOk: false, warning: "trial_failed" });
  });

  it("reads a null warning as nothing to warn about", () => {
    const ev = f.hitlPublishRequested(1, "act-1", null);
    expect(readPublishNotice(ev.data.preview)).toMatchObject({ warning: null });
  });

  it("returns null for a publish preview that predates v2, so nothing is invented", () => {
    expect(readPublishNotice({ client_ref: "boreal", from_version: 7, to_version: 8 })).toBeNull();
  });

  it("ignores a warning key outside the closed set", () => {
    expect(readPublishNotice({ trial_ran: true, warning_key: "meteor_strike" })).toMatchObject({ warning: null });
  });
});

// ── §6 · the pause ─────────────────────────────────────────────────────

describe("budget.paused — a pause, not an error (v2 §6)", () => {
  it("sets the pause and leaves a NEUTRAL mark where the work stopped", () => {
    const s = apply(emptyCompanionState, "run-a", [f.budgetPaused(1)]);
    expect(s.paused).toMatchObject({ used: 2000000, cap: 2000000, period: "2026-08", scope: "partner" });
    const notice = s.items.find((i) => i.kind === "notice");
    expect(notice).toMatchObject({ code: "paused" });
    // Not the error code — that is the whole point of the v2 split.
    expect(notice).not.toMatchObject({ code: "error" });
  });

  it("keeps the history: nothing already in the timeline is dropped", () => {
    let s = apply(emptyCompanionState, "run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "voy por aquí")]);
    s = apply(s, "run-a", [f.budgetPaused(3)]);
    expect(s.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "voy por aquí" });
  });

  it("`run.completed{status:paused}` is terminal and is NOT painted as an error", () => {
    const s = apply(emptyCompanionState, "run-a", [f.runStarted(1, "run-a"), f.runCompleted(2, "run-a", "paused")]);
    expect(s.runStatus).toBe("paused");
    expect(s.items.find((i) => i.kind === "notice")).toMatchObject({ code: "paused" });
    // Without the explicit branch this would fall through to "completed"
    // and the cut would be invisible.
    expect(s.runStatus).not.toBe("completed");
  });

  it("the pause survives a thread switch: it belongs to the partner (§6.1)", () => {
    const s = apply(emptyCompanionState, "run-a", [f.budgetPaused(1)]);
    const reset = companionReducer(s, { type: "reset" });
    expect(reset.items).toHaveLength(0);
    expect(reset.paused).not.toBeNull();
  });

  it("the 409 sets the pause WITHOUT a timeline entry — nothing happened in the thread", () => {
    // §6.2: the body carries the snapshot so no second request is needed.
    const pause = readBudgetPause({
      code: "budget_paused",
      used: 2000000,
      cap: 2000000,
      period: "2026-08",
      resets_at: "2026-09-01T00:00:00Z",
    });
    expect(pause).not.toBeNull();
    const s = companionReducer(emptyCompanionState, { type: "budget_paused", pause: pause! });
    expect(s.paused).toMatchObject({ used: 2000000, cap: 2000000 });
    expect(s.items).toHaveLength(0);
    expect(s.runStatus).toBe("idle");
  });

  it("a pending confirmation stays pending through a pause — `resume` starts no new work", () => {
    let s = apply(emptyCompanionState, "run-a", [f.hitlRequested(1, "act-1")]);
    s = apply(s, "run-a", [f.budgetPaused(2)]);
    const card = s.items.find((i) => i.kind === "action");
    expect(card).toMatchObject({ state: "pending" });
  });
});
