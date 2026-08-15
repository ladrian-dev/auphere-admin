/**
 * Better Auth handler. Public sign-up is refused here: accounts are only
 * created server-side while accepting an invitation.
 */
import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

const handler = toNextJsHandler(auth);

function blocked(request: Request): Response | null {
  const path = new URL(request.url).pathname;
  if (path.startsWith("/api/auth/sign-up")) {
    return new Response(JSON.stringify({ detail: "sign-up is by invitation only" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  }
  return null;
}

export const GET = handler.GET;
export async function POST(request: Request) {
  return blocked(request) ?? handler.POST(request);
}
