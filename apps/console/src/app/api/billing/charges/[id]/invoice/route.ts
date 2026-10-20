import { NextResponse } from "next/server";
import { z } from "zod";

import { backendFor } from "@/lib/backend";
import { can, resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * «Ver factura» of a card charge (owner, 2026-10-20): straight to Stripe's
 * invoice page. The API only resolves the partner's own charges, and reads the
 * link fresh from Stripe. Anything that fails lands back on Facturación with a
 * line that says the invoice could not be opened — never a JSON page.
 */
export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const back = (reason: string) => NextResponse.redirect(new URL(`/billing?invoice=${reason}`, request.url), 303);
  const id = z.string().uuid().safeParse((await ctx.params).id);
  if (!id.success) return back("missing");
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return NextResponse.redirect(new URL("/login?from=/billing", request.url), 303);
  if (!can(res.principal.role, "billing:read")) return back("missing");
  try {
    const { url } = await backendFor(res.principal).chargeInvoice(id.data);
    return NextResponse.redirect(url, 303);
  } catch {
    return back("missing");
  }
}
