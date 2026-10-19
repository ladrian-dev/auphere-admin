import { NextResponse, type NextRequest } from "next/server";

import { OWNER_LINK_COOKIE, OWNER_LINK_MAX_AGE, TOKEN_SHAPE } from "../link-cookie";

/**
 * Spec 040: where the shared link lands. The token goes into an httpOnly
 * cookie and the browser is sent to `/connect/whatsapp`, so the page that
 * loads Meta's SDK never has the token in its address or its history.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const res = NextResponse.redirect(new URL("/connect/whatsapp", request.url), 303);
  res.headers.set("Referrer-Policy", "no-referrer");
  res.headers.set("Cache-Control", "no-store");
  if (TOKEN_SHAPE.test(token)) {
    res.cookies.set(OWNER_LINK_COOKIE, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/connect",
      maxAge: OWNER_LINK_MAX_AGE,
    });
  } else {
    res.cookies.delete({ name: OWNER_LINK_COOKIE, path: "/connect" });
  }
  return res;
}
