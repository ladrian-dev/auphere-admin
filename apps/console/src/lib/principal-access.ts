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
 *
 * Spec 030 adds a second kind of person: the **client user**, bound to one
 * client of a partner, whose only permission is the modules Auphere chose for
 * that client. The API resolves which kind from the table the account lives
 * in; this module only carries the answer.
 */

/** The client console's modules, in sidebar order (Panel, Bandeja, Consumo). */
export const CLIENT_MODULES = ["panel", "inbox", "usage"] as const;
export type ClientModule = (typeof CLIENT_MODULES)[number];

type PrincipalBase = {
  userId: string;
  email: string;
  name: string;
  locale: "es" | "en";
  membershipId: string;
  partnerId: string;
  partnerSlug: string;
  partnerName: string;
  consoleEnabled: boolean;
};

export type PartnerPrincipal = PrincipalBase & { kind: "partner"; role: Role };

export type ClientPrincipal = PrincipalBase & {
  kind: "client";
  role: "client";
  clientName: string;
  /** Never empty: a client without modules resolves as `no-membership`. */
  modules: ClientModule[];
};

export type Principal = PartnerPrincipal | ClientPrincipal;

export type PrincipalResolution =
  | { kind: "anonymous" }
  | { kind: "no-membership"; email: string }
  | { kind: "suspended"; email: string; clientName?: string }
  | { kind: "disabled"; email: string; partnerName: string; clientName?: string }
  | { kind: "ok"; principal: Principal };

function isClientModule(m: string): m is ClientModule {
  return (CLIENT_MODULES as readonly string[]).includes(m);
}

/**
 * Spec 031 (R3.2): the API sends the modules already in sidebar order
 * (`ClientAccess.ordered_modules()`), and that order is the only one — the
 * console and the phone app both paint it as it comes. This only drops what the
 * console cannot render yet and repeats; it never re-sorts.
 */
function clientModules(raw: string[]): ClientModule[] {
  return raw.filter(isClientModule).filter((m, i, all) => all.indexOf(m) === i);
}

export function toResolution(p: ApiPrincipal): PrincipalResolution {
  const email = p.email;
  const isClient = p.kind === "client";
  const clientName = isClient ? { clientName: p.client_name ?? "" } : {};
  switch (p.access) {
    case "no_membership":
      return { kind: "no-membership", email };
    case "suspended":
      return { kind: "suspended", email, ...clientName };
    case "disabled":
      return { kind: "disabled", email, partnerName: p.partner_name ?? "", ...clientName };
    case "ok":
      break;
  }
  // `access === "ok"` guarantees the partner fields on the API side; this
  // fallback exists only so a contract drift degrades to /no-access instead
  // of rendering a half-built shell with empty ids.
  if (!p.membership_id || !p.partner_id || !p.role) return { kind: "no-membership", email };
  const base: PrincipalBase = {
    userId: p.user_id,
    email,
    name: p.display_name ?? "",
    locale: p.locale === "en" ? "en" : "es",
    membershipId: p.membership_id,
    partnerId: p.partner_id,
    partnerSlug: p.partner_slug ?? "",
    partnerName: p.partner_name ?? "",
    consoleEnabled: p.console_enabled,
  };
  if (isClient) {
    const modules = clientModules(p.modules ?? []);
    if (p.role !== "client" || modules.length === 0) return { kind: "no-membership", email };
    return {
      kind: "ok",
      principal: { ...base, kind: "client", role: "client", clientName: p.client_name ?? "", modules },
    };
  }
  return { kind: "ok", principal: { ...base, kind: "partner", role: p.role as Role } };
}

/** Where a client lands: its first module, in the order the API sent. */
export function firstModulePath(modules: readonly ClientModule[]): string {
  const first = modules[0] ?? "panel";
  return first === "panel" ? "/" : first === "inbox" ? "/inbox" : "/usage";
}

/**
 * The module a console path belongs to for a client person, or `null` when the
 * path is not a client's (spec 030, T111). The console layout uses it to send
 * anything else to the first module before the page streams; the page guards
 * and the API stay the authority. `page-guards.test.ts` ties it to the pages
 * that call `requireClientPrincipal`.
 */
export function clientModuleOfPath(pathname: string): ClientModule | null {
  if (pathname === "/") return "panel";
  if (pathname === "/inbox") return "inbox";
  if (pathname === "/usage") return "usage";
  return null;
}

/**
 * Spec 031 (R7.3): the client person's own account pages. They belong to the
 * person, not to a module — every client person has them, whatever modules its
 * client has. `page-guards.test.ts` ties this list to the pages that call
 * `requireClientAccount`.
 */
export const CLIENT_ACCOUNT_PATHS = ["/account/phones"] as const;

export function isClientAccountPath(pathname: string): boolean {
  return (CLIENT_ACCOUNT_PATHS as readonly string[]).includes(pathname);
}
