"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { ADS_PERIODS, type AdsReport } from "@/lib/backend/ads";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 076 (requisito 3): el informe de anuncios de un cliente con otro periodo.
 * `conversations:read`; la API vuelve a comprobar el cliente bajo el partner.
 */

const schema = z.object({
  ref: z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/),
  days: z.union([z.literal(ADS_PERIODS[0]), z.literal(ADS_PERIODS[1]), z.literal(ADS_PERIODS[2])]),
});

export async function adsReportAction(raw: unknown): Promise<ActionResult<AdsReport>> {
  const body = schema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "conversations:read")) {
    return { ok: false, status: 403, message: "forbidden" };
  }
  return run(() => backendFor(principal).adsReport(body.ref, body.days));
}
