import { describe, expect, it } from "vitest";

import {
  cleanPlaceholders,
  elapsedSeconds,
  missingPlaceholders,
  nextStage,
  planStages,
  runOutcome,
  slugify,
  stageReducer,
} from "../wizard-state";

describe("wizard-state", () => {
  it("plans stages from the choices", () => {
    expect(planStages({ seed_template: null, publish_now: true }).map((s) => s.status)).toEqual([
      "pending",
      "skipped",
      "skipped",
      "pending",
    ]);
    expect(planStages({ seed_template: "generic_v1", publish_now: false }).map((s) => s.status)).toEqual([
      "pending",
      "pending",
      "skipped",
      "pending",
    ]);
    expect(planStages({ seed_template: "generic_v1", publish_now: true }).every((s) => s.status === "pending")).toBe(true);
  });

  it("reduces stage events and reports the outcome", () => {
    let st = planStages({ seed_template: "generic_v1", publish_now: false });
    expect(runOutcome(st)).toBe("idle");
    expect(nextStage(st)).toBe("create");
    st = stageReducer(st, { type: "start", key: "create", at: 1000 });
    expect(runOutcome(st)).toBe("running");
    st = stageReducer(st, { type: "done", key: "create", at: 1500 });
    st = stageReducer(st, { type: "start", key: "seed", at: 1500 });
    st = stageReducer(st, { type: "fail", key: "seed", at: 2200, error: "missing placeholder" });
    expect(runOutcome(st)).toBe("partial");
    expect(nextStage(st)).toBe("seed");
    expect(st[1]!.error).toBe("missing placeholder");
    st = stageReducer(st, { type: "start", key: "seed", at: 3000 });
    st = stageReducer(st, { type: "done", key: "seed", at: 3400 });
    st = stageReducer(st, { type: "start", key: "channel", at: 3400 });
    st = stageReducer(st, { type: "done", key: "channel", at: 3400 });
    expect(runOutcome(st)).toBe("done");
    expect(nextStage(st)).toBeNull();
    expect(elapsedSeconds(st)).toBe(2.4);
  });

  it("validates placeholders", () => {
    const defs = [
      { key: "tenant.address", required: true, secret: false, kind: "text" as const, example: null },
      { key: "agent.name", required: false, secret: false, kind: "text" as const, example: "Alex" },
    ];
    expect(missingPlaceholders(defs, {})).toEqual(["tenant.address"]);
    expect(missingPlaceholders(defs, { "tenant.address": "  " })).toEqual(["tenant.address"]);
    expect(missingPlaceholders(defs, { "tenant.address": "x" })).toEqual([]);
    expect(cleanPlaceholders({ a: " x ", b: "", c: "  " })).toEqual({ a: "x" });
  });

  it("slugifies names into refs", () => {
    expect(slugify("Clínica Boreal — Caracas")).toBe("clinica-boreal-caracas");
  });
});
