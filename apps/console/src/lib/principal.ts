import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { sql } from "@/db/client";

import { getSession } from "./session";

/**
 * Who is calling, in which partner, with what role — resolved from the
 * Better Auth session + ``public.partner_memberships`` (read-only, one
 * indexed query, memoised per request with ``React.cache``).
 *
 * This is the console's HALF of authorization: it decides what to render
 * and what to attempt. The API re-verifies the same membership on every
 * call and derives permissions from its own map (``core/console_auth.py``),
 * so a bug here can never widen what a partner may do.
 */
import type { Role } from "./permissions";

export type Principal = {
  userId: string;
  email: string;
  name: string;
  locale: "es" | "en";
  membershipId: string;
  partnerId: string;
  partnerSlug: string;
  partnerName: string;
  role: Role;
  consoleEnabled: boolean;
};

type MembershipRow = {
  membership_id: string;
  partner_id: string;
  partner_slug: string;
  partner_name: string;
  role: Role;
  status: string;
  partner_status: string;
  console_enabled: boolean;
};

const loadMembership = cache(async (userId: string): Promise<MembershipRow | null> => {
  const rows = await sql<MembershipRow[]>`
    SELECT m.id::text AS membership_id,
           m.partner_id::text AS partner_id,
           p.slug AS partner_slug,
           p.name AS partner_name,
           m.role,
           m.status,
           p.status AS partner_status,
           p.console_enabled
      FROM public.partner_memberships m
      JOIN public.partners p ON p.id = m.partner_id
     WHERE m.user_id = ${userId}
     LIMIT 1
  `;
  return rows[0] ?? null;
});

export type PrincipalResolution =
  | { kind: "anonymous" }
  | { kind: "no-membership"; email: string }
  | { kind: "suspended"; email: string }
  | { kind: "disabled"; email: string; partnerName: string }
  | { kind: "ok"; principal: Principal };

export const resolvePrincipal = cache(async (): Promise<PrincipalResolution> => {
  const session = await getSession();
  if (!session) return { kind: "anonymous" };
  const row = await loadMembership(session.user.id);
  const email = session.user.email;
  if (!row) return { kind: "no-membership", email };
  if (row.status !== "active" || row.partner_status !== "active") return { kind: "suspended", email };
  const locale = (session.user as { locale?: string }).locale === "en" ? "en" : "es";
  const principal: Principal = {
    userId: session.user.id,
    email,
    name: session.user.name,
    locale,
    membershipId: row.membership_id,
    partnerId: row.partner_id,
    partnerSlug: row.partner_slug,
    partnerName: row.partner_name,
    role: row.role,
    consoleEnabled: row.console_enabled,
  };
  if (!row.console_enabled) return { kind: "disabled", email, partnerName: row.partner_name };
  return { kind: "ok", principal };
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
