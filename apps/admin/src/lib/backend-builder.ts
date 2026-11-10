/**
 * Spec 047 (T087, T090, T100): the API of the agent builder's quality —
 * the sector test catalog, the judge's calibration and the builder's
 * evaluation (`api/admin/sector_tests.py`). Apart from `backend.ts`, like
 * `backend-models.ts`; same `call`, same token.
 *
 * Every write names the operator (`X-Operator-Id`). Server-side only.
 */

import "server-only";

import { call } from "@/lib/backend";

/** `services/testing/sector_catalog.py` (`SectorCriterion`). */
export type SectorCriterion = { key: string; text: string };

/** `services/testing/sector_catalog.py` (`SectorTest`): no other field is accepted. */
export type SectorTest = {
  key: string;
  name: string;
  persona: string;
  first_message: string;
  plan: string;
  expected_state: Record<string, unknown>;
  criteria: SectorCriterion[];
  critical: boolean;
};

/** One sector with its version in force; without one, `version` is null. */
export type SectorCatalog = {
  sector: string;
  name: string;
  version: number | null;
  published_at: string | null;
  published_by: string | null;
  tests: SectorTest[];
};

/** `services/testing/judge.py`: «No sé» is `unknown`. */
export type JudgeVerdict = "pass" | "fail" | "unknown";

export type CalibrationItem = {
  /** The example of the labelled set (`cal-01`…). */
  id: string;
  /** The criterion of that example. */
  key: string;
  label: JudgeVerdict;
  judge: JudgeVerdict;
  match: boolean;
};

export type CalibrationScores = {
  agreement: number;
  threshold: number;
  set_version: number;
  items: CalibrationItem[];
};

/**
 * A row of `latest_report`: the certification of the task `judge` of one
 * deployment. `quality` is the agreement; it travels as a decimal string
 * (a `Decimal` under `dict[str, Any]`), so read it with `Number()`.
 */
export type CalibrationReport = {
  deployment_id: string;
  model_id: string;
  quality: number | string;
  passed: boolean;
  scores: Partial<CalibrationScores>;
  certified_at: string;
  invalidated_at: string | null;
};

/** What `POST /admin/builder/judge-calibration` answers. */
export type CalibrationRun = CalibrationScores & { deployment_id: string; passed: boolean };

type EvalMetrics = {
  validator_first_pass_pct: number | null;
  sector_pass_unedited_pct: number | null;
  draft_p90_ms: number | null;
};

/** `services/builder/evaluation.py` (`history`): the newest first. */
export type EvalRun = {
  id: string;
  bank_version: string;
  created_at: string;
  created_by: string;
  validator_first_pass_pct: number;
  sector_pass_unedited_pct: number | null;
  draft_p90_ms: number | null;
  /** The difference with the run before; null on the first one. */
  vs_previous: EvalMetrics | null;
};

const op = (operatorId: string) => ({ "X-Operator-Id": operatorId });

export const builderBackend = {
  sectorTests: () => call<SectorCatalog[]>("/admin/builder/sector-tests"),
  publishSectorTests: (sector: string, tests: SectorTest[], operatorId: string) =>
    call<SectorCatalog>(`/admin/builder/sector-tests/${encodeURIComponent(sector)}`, {
      method: "POST",
      body: { tests },
      headers: op(operatorId),
    }),

  calibrations: () => call<CalibrationReport[]>("/admin/builder/judge-calibration"),
  calibrate: (deploymentId: string, operatorId: string) =>
    call<CalibrationRun>("/admin/builder/judge-calibration", {
      method: "POST",
      body: { deployment_id: deploymentId },
      headers: op(operatorId),
    }),

  evalRuns: () => call<EvalRun[]>("/admin/builder/eval"),
  runEval: (limit: number | null, operatorId: string) =>
    call<EvalRun>("/admin/builder/eval", {
      method: "POST",
      body: limit ? { limit } : {},
      headers: op(operatorId),
    }),
};
