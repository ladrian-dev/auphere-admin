import { NextResponse, type NextRequest } from "next/server";

import { OWNER_LINK_MAX_AGE, TOKEN_SHAPE, isSocialLinkKind, ownerLinkCookie } from "../../whatsapp/link-cookie";

/**
 * Spec 085: where an Instagram or Messenger link lands, like WhatsApp's
 * (spec 040). The token goes into the channel's httpOnly cookie and the
 * browser is sent to `/connect/{kind}`, so the page that loads Meta's SDK
 * never has the token in its address or its history (7.4).
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ kind: string; token: string }> }) {
  const { kind, token } = await params;
  if (!isSocialLinkKind(kind)) return new NextResponse(null, { status: 404 });
  const cookie = ownerLinkCookie(kind);
  const res = NextResponse.redirect(new URL(`/connect/${kind}`, request.url), 303);
  res.headers.set("Referrer-Policy", "no-referrer");
  res.headers.set("Cache-Control", "no-store");
  if (TOKEN_SHAPE.test(token)) {
    res.cookies.set(cookie, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/connect",
      maxAge: OWNER_LINK_MAX_AGE,
    });
  } else {
    res.cookies.delete({ name: cookie, path: "/connect" });
  }
  return res;
}
