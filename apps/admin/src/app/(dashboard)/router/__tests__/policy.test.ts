import { describe, expect, it } from "vitest";

import type { ProfilePolicyJson } from "@/lib/backend-models";

import { OUTCOME_LABEL, policyFromRows, rejectionLabel, rowsFromPolicy, type Limits } from "../policy";

const POLICY: ProfilePolicyJson = {
  tasks: {
    classify: { min_quality: 0.9, max_cost_per_call_micros: 200, escalate_to: null, reasoning: "none", judge_sampling: null, reserve: "openai/gpt-5.6-luna" },
    tool_turn: { min_quality: 0.92, max_cost_per_call_micros: 4000, escalate_to: "medium", reasoning: "low", judge_sampling: "by_risk", reserve: null },
  },
  turn_cost_ceiling_micros: 80000,
  max_calls_per_turn: 12,
  max_escalations_per_hour: 3,
  latency_p95_ms: { classify: 800 },
};
const CEILINGS = { max_calls_per_turn: 12, max_escalations_per_hour: 3 };
const LIMITS: Limits = { max_calls_per_turn: "12", max_escalations_per_hour: "3", turn_cost_ceiling_micros: "80000" };

/** Spec 047 (T150, 40.13, 54.2): the router's policy, row by row. */
describe("the profile policy form", () => {
  it("round-trips a policy: what is not edited stays as it was", () => {
    const rows = rowsFromPolicy(POLICY);
    expect(rows.map((r) => r.task)).toEqual(["classify", "tool_turn"]);
    expect(rows[0]).toMatchObject({ min_quality: "0.9", reserve: "openai/gpt-5.6-luna", judge_sampling: "" });
    const back = policyFromRows(POLICY, rows, LIMITS, CEILINGS);
    expect(back).toEqual({ ok: true, policy: POLICY });
  });

  it("writes what the operator changed, in numbers", () => {
    const rows = rowsFromPolicy(POLICY);
    rows[0] = { ...rows[0]!, min_quality: "0,93", judge_sampling: "0.1", reserve: "" };
    const back = policyFromRows(POLICY, rows, { ...LIMITS, max_calls_per_turn: "10" }, CEILINGS);
    expect(back.ok).toBe(true);
    if (!back.ok) return;
    expect(back.policy.tasks.classify).toMatchObject({ min_quality: 0.93, judge_sampling: 0.1, reserve: null });
    expect(back.policy.max_calls_per_turn).toBe(10);
  });

  it("never raises the ceilings of 40.10, and checks every value", () => {
    const rows = rowsFromPolicy(POLICY);
    rows[1] = { ...rows[1]!, min_quality: "1.4", escalate_to: "huge", reasoning: "max", max_cost: "-3" };
    const back = policyFromRows(POLICY, rows, { ...LIMITS, max_calls_per_turn: "20" }, CEILINGS);
    expect(back.ok).toBe(false);
    if (back.ok) return;
    expect(Object.keys(back.errors).sort()).toEqual([
      "max_calls_per_turn",
      "tool_turn.escalate_to",
      "tool_turn.max_cost",
      "tool_turn.min_quality",
      "tool_turn.reasoning",
    ]);
  });
});

describe("the router's words", () => {
  it("says why a deployment was discarded", () => {
    expect(rejectionLabel("retention")).toMatch(/retención cero/);
    expect(rejectionLabel("capability:tools")).toMatch(/tools/);
    expect(rejectionLabel("agent_pinned:status")).toMatch(/fijado/);
    expect(rejectionLabel("algo_nuevo")).toBe("algo_nuevo");
  });

  it("names every outcome", () => {
    expect(OUTCOME_LABEL.no_model).toBe("Sin modelo disponible");
    expect(OUTCOME_LABEL.reserve_model).toMatch(/reserva/);
  });
});
