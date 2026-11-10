"use server";

import { revalidatePath } from "next/cache";

import { BackendError } from "@/lib/backend";
import {
  sectorGuidesBackend,
  type GeneratedGuide,
  type PromoteBody,
  type ReviewBody,
  type SectorGuide,
} from "@/lib/backend-sector-guides";
import { requireOperator } from "@/lib/session";

import { LIST_PATH, guideFailure, guidePath, type GuideResult } from "./sector-guides";

function failed(err: unknown, action: "review" | "promote") {
  if (err instanceof BackendError) return guideFailure(err.status, err.body, action);
  return { ok: false as const, error: err instanceof Error ? err.message : String(err) };
}

/**
 * Spec 047 (T201, 58.5): mark a client's generated guide as reviewed, with the
 * corrections (`guide`, `tests`) and a note. The API checks the client's data
 * on what stays saved; with some left it writes nothing and says where.
 */
export async function reviewGeneratedGuideAction(
  tenantId: string,
  guideId: string,
  body: ReviewBody,
): Promise<GuideResult<GeneratedGuide>> {
  const operator = await requireOperator();
  try {
    const data = await sectorGuidesBackend.review(tenantId, guideId, body, operator.id);
    revalidatePath(LIST_PATH);
    revalidatePath(guidePath(tenantId, guideId));
    return { ok: true, data: data as GeneratedGuide };
  } catch (err) {
    return failed(err, "review");
  }
}

/**
 * Spec 047 (T201, 58.5, D66): «Convertir en guía de Auphere». A reviewed guide
 * without client data becomes a platform guide with a new key, and its 12 tests
 * version 1 of that key in the sector catalog, in one transaction.
 */
export async function promoteGeneratedGuideAction(
  tenantId: string,
  guideId: string,
  body: PromoteBody,
): Promise<GuideResult<SectorGuide>> {
  const operator = await requireOperator();
  try {
    const data = await sectorGuidesBackend.promote(tenantId, guideId, body, operator.id);
    revalidatePath(LIST_PATH);
    revalidatePath(guidePath(tenantId, guideId));
    return { ok: true, data: data as SectorGuide };
  } catch (err) {
    return failed(err, "promote");
  }
}
