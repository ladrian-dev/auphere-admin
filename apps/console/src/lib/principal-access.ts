import type { ApiPrincipal } from "./backend";
import type { Role } from "./permissions";

/**
 * The pure half of `lib/principal.ts`: API payload → what the console
 * renders. Lives in its own module (no `server-only`) so the mapping is
 * unit-testable without a request.
 *
 * The four `access` values are the API's answer to "may this person use
 * the console?", and they are the same four cases the BFF used to derive
 * from SQL before ADR-032 — the copy on `/no-access` depends on telling
 * them apart.
 */
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

export type PrincipalResolution =
  | { kind: "anonymous" }
  | { kind: "no-membership"; email: string }
  | { kind: "suspended"; email: string }
  | { kind: "disabled"; email: string; partnerName: string }
  | { kind: "ok"; principal: Principal };

export function toResolution(p: ApiPrincipal): PrincipalResolution {
  const email = p.email;
  switch (p.access) {
    case "no_membership":
      return { kind: "no-membership", email };
    case "suspended":
      return { kind: "suspended", email };
    case "disabled":
      return { kind: "disabled", email, partnerName: p.partner_name ?? "" };
    case "ok":
      break;
  }
  // `access === "ok"` guarantees the partner fields on the API side; this
  // fallback exists only so a contract drift degrades to /no-access instead
  // of rendering a half-built shell with empty ids.
  if (!p.membership_id || !p.partner_id || !p.role) return { kind: "no-membership", email };
  return {
    kind: "ok",
    principal: {
      userId: p.user_id,
      email,
      name: p.display_name ?? "",
      locale: p.locale === "en" ? "en" : "es",
      membershipId: p.membership_id,
      partnerId: p.partner_id,
      partnerSlug: p.partner_slug ?? "",
      partnerName: p.partner_name ?? "",
      role: p.role as Role,
      consoleEnabled: p.console_enabled,
    },
  };
}
