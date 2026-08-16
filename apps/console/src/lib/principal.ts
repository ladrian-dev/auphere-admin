import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { consoleService } from "./backend";
import { toResolution, type Principal, type PrincipalResolution } from "./principal-access";
import { getSessionToken } from "./session";

/**
 * Who is calling, in which partner, with what role — resolved by the API
 * from the session cookie (`POST /console/auth/session`), memoised per
 * request with `React.cache`.
 *
 * Until ADR-032 this file ran SQL: it read `public.partner_memberships`
 * through a Drizzle/postgres.js pool. That is gone — the console has no
 * database, so the private Aurora is no longer something Vercel has to
 * reach. The shape of the answer is deliberately unchanged, because this
 * is still only the console's HALF of authorization: it decides what to
 * render and what to attempt, and the API re-verifies the same membership
 * on every call (`core/console_auth.py`), so a bug here can never widen
 * what a partner may do.
 */
export type { Principal, PrincipalResolution } from "./principal-access";

export const resolvePrincipal = cache(async (): Promise<PrincipalResolution> => {
  const token = await getSessionToken();
  if (!token) return { kind: "anonymous" };
  const principal = await consoleService.session(token);
  if (!principal) return { kind: "anonymous" };
  return toResolution(principal);
});

/** Redirects to the right page when the caller is not a usable principal. */
export async function requirePrincipal(from?: string): Promise<Principal> {
  const res = await resolvePrincipal();
  switch (res.kind) {
    case "anonymous":
      redirect(from ? `/login?from=${encodeURIComponent(from)}` : "/login");
    case "no-membership":
    case "suspended":
    case "disabled":
      redirect("/no-access");
    case "ok":
      return res.principal;
  }
}

export { PERMISSIONS, can, type Permission, type Role } from "./permissions";
