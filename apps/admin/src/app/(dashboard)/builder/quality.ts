/**
 * Spec 059 (T032, T034; 5.5, 5.6): the two reads of the builder's quality
 * that stopped being bare lists. `GET /admin/builder/judge-calibration` now
 * also says which model is the judge and whether it is calibrated, and
 * `GET /admin/builder/eval` how many descriptions the bank really has.
 *
 * They live here, next to the screens that read them, because
 * `lib/backend-builder.ts` still types both reads as arrays
 * (`calibrations`, `evalRuns`). Same `call`, same token. Server-side only.
 */

import "server-only";

import { call } from "@/lib/backend";
import type { CalibrationReport, EvalRun } from "@/lib/backend-builder";

/** `api/admin/sector_tests.py` (`calibration_report`). */
export type JudgeCalibrationPage = {
  /** The model that judges the agents' tests in this deployment (`default_models()["judge"]`). */
  judge_model: string;
  /** Whether that model has a passed calibration still in force: only then does it block. */
  judge_calibrated: boolean;
  /** Every calibration, the newest first; another model's does not make the judge block. */
  reports: CalibrationReport[];
};

/** `api/admin/sector_tests.py` (`eval_history`). */
export type EvalPage = {
  /** How many descriptions the bank has (`len(bank())`). */
  bank_size: number;
  /** The runs, the newest first. */
  runs: EvalRun[];
};

export const builderQuality = {
  judgeCalibration: () => call<JudgeCalibrationPage>("/admin/builder/judge-calibration"),
  evalRuns: () => call<EvalPage>("/admin/builder/eval"),
};
