"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import {
  builderBackend,
  type CalibrationRun,
  type EvalRun,
  type SectorCatalog,
  type SectorTest,
} from "@/lib/backend-builder";
import { requireOperator } from "@/lib/session";

import { CALIBRATION_ERRORS } from "./labels";
import { PUBLISH_ERRORS } from "./sector-tests/sector-tests";

/**
 * Spec 047 (T090, 54.10): a new version of a sector's 12 tests. The suites of
 * the agents that already exist do not change.
 */
export async function publishSectorTestsAction(
  sector: string,
  tests: SectorTest[],
): Promise<Result<SectorCatalog>> {
  const operator = await requireOperator();
  try {
    const data = await builderBackend.publishSectorTests(sector, tests, operator.id);
    revalidatePath("/builder/sector-tests");
    return { ok: true, data: data as SectorCatalog };
  } catch (err) {
    return toFailure(err, PUBLISH_ERRORS);
  }
}

/**
 * Spec 047 (T087, 21.8): run a deployment's judge over the labelled set and
 * keep its agreement as the certification of the task `judge`. Auphere pays.
 */
export async function calibrateJudgeAction(deploymentId: string): Promise<Result<CalibrationRun>> {
  const operator = await requireOperator();
  try {
    const data = await builderBackend.calibrate(deploymentId, operator.id);
    revalidatePath("/builder/judge-calibration");
    revalidatePath("/certifications");
    return { ok: true, data: data as CalibrationRun };
  } catch (err) {
    return toFailure(err, CALIBRATION_ERRORS);
  }
}

/**
 * Spec 047 (T100, 54.4): run the builder over the bank (or its first `limit`
 * descriptions) and keep the figures. It writes nothing in any client.
 */
export async function runEvalAction(limit: number | null): Promise<Result<EvalRun>> {
  const operator = await requireOperator();
  try {
    const data = await builderBackend.runEval(limit, operator.id);
    revalidatePath("/builder/eval");
    return { ok: true, data: data as EvalRun };
  } catch (err) {
    return toFailure(err);
  }
}
