import { NextResponse } from "next/server";

import { backend } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

export const dynamic = "force-dynamic";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * «Ver factura» of a partner's card charge (owner, 2026-10-20): straight to
 * Stripe's invoice page, read fresh by the API. Anything that fails lands back
 * on the partner's Facturas tab with a line that says so.
 */
export async function GET(
  request: Request,
  ctx: { params: Promise<{ id: string; chargeId: string }> },
): Promise<Response> {
  const { id, chargeId } = await ctx.params;
  const operator = await requireOperator();
  const back = NextResponse.redirect(new URL(`/partners/${id}/money?invoice=missing`, request.url), 303);
  if (operator.access !== "ok" || !UUID.test(id) || !UUID.test(chargeId)) return back;
  try {
    const res = await backend.getPartnerChargeInvoice(id, chargeId);
    return res?.url ? NextResponse.redirect(res.url, 303) : back;
  } catch {
    return back;
  }
}
