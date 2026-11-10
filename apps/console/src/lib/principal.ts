import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { consoleService } from "./backend";
import {
  firstModulePath,
  firstPartnerModulePath,
  toResolution,
  type ClientModule,
  type ClientPrincipal,
  type PartnerModule,
  type PartnerPrincipal,
  type Principal,
  type PrincipalResolution,
} from "./principal-access";
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
export type {
  ClientModule,
  ClientPrincipal,
  PartnerModule,
  PartnerPrincipal,
  Principal,
  PrincipalResolution,
} from "./principal-access";
export { firstModulePath, firstPartnerModulePath } from "./principal-access";

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

/**
 * Spec 030: the gate of every partner page. A client user who asks for one
 * goes to its first module — no screen that explains what it does not have
 * (constitution §V). The API would answer 403 anyway; this keeps the shell
 * and its errors away from someone they are not for.
 */
export async function requirePartnerPrincipal(from?: string): Promise<PartnerPrincipal> {
  const principal = await requirePrincipal(from);
  if (principal.kind === "client") redirect(firstModulePath(principal.modules));
  return principal;
}

/**
 * Spec 030: the gate of every client-console page. A partner member goes
 * home; a client whose client lacks `module` goes to its first module.
 */
/**
 * Spec 032: the gate of a partner section. A partner whose console does not
 * have `module` goes to its first module — no screen explaining what it does
 * not have (§V). A client user passes through: its own pages gate it with
 * `requireClientPrincipal`.
 */
export async function requirePartnerModule(module: PartnerModule, from?: string): Promise<void> {
  const principal = await requirePrincipal(from);
  if (principal.kind === "partner" && !principal.modules.includes(module)) {
    redirect(firstPartnerModulePath(principal.modules));
  }
}

export async function requireClientPrincipal(module: ClientModule, from?: string): Promise<ClientPrincipal> {
  const principal = await requirePrincipal(from);
  if (principal.kind !== "client") redirect("/");
  if (!principal.modules.includes(module)) redirect(firstModulePath(principal.modules));
  return principal;
}

/**
 * Spec 031 (R7.3): the gate of a client person's own account page («Tus
 * teléfonos»). Any client person has it; a partner member goes home.
 */
export async function requireClientAccount(from?: string): Promise<ClientPrincipal> {
  const principal = await requirePrincipal(from);
  if (principal.kind !== "client") redirect("/");
  return principal;
}

export { PERMISSIONS, can, type Permission, type Role } from "./permissions";
