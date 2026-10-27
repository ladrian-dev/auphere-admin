import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { CompanionLauncher } from "@/components/companion/companion-launcher";
import { ConsoleShellV1 } from "@/components/shell/console-shell-v1";
import { ConsoleShellV2 } from "@/components/shell/console-shell-v2";
import { NAV_COLLAPSED, NAV_COOKIE, resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, type ConsoleVersion } from "@/lib/backend";
import { clientModuleOfPath, isClientAccountPath } from "@/lib/principal-access";
import { firstModulePath, requirePrincipal, type PartnerPrincipal } from "@/lib/principal";

/**
 * Spec 047 (R55.2): the frame this partner sees, from `GET /console/me`. One
 * call per request (React `cache`). Anything but a clear `v2` — an older API,
 * a timeout, an error — is today's console: a partner is never moved to the
 * new one by accident.
 */
const consoleVersionOf = cache(async (principal: PartnerPrincipal): Promise<ConsoleVersion> => {
  try {
    return resolveConsoleVersion(await backendFor(principal).me());
  } catch {
    return "v1";
  }
});

/**
 * The console shell (CP-07). ``requirePrincipal`` is the real gate: an
 * anonymous visitor goes to /login, a signed-in user with no partner (or a
 * partner not yet enabled) goes to /no-access.
 *
 * Spec 047 (T004): the frame is chosen here. A partner with the new console
 * activated gets `ConsoleShellV2`; every other partner, and every client
 * person (spec 030), gets today's (`ConsoleShellV1`), unchanged.
 */
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const principal = await requirePrincipal();
  if (principal.kind === "client") {
    // Spec 030 (T111): a client person who types a path that is not theirs
    // goes to its first module HERE, before anything streams — a real 307.
    // The page guard would send them too, but from under `loading.tsx`, where
    // the redirect broke Next's Router (React #310) and showed «This page
    // couldn't load» for a second. The page guards stay the gate.
    const path = (await headers()).get("x-pathname");
    // Spec 031: the person's own account pages are theirs whatever the modules.
    const owner = path === null ? null : clientModuleOfPath(path);
    if (path !== null && !isClientAccountPath(path) && (owner === null || !principal.modules.includes(owner))) {
      redirect(firstModulePath(principal.modules));
    }
  }
  const { t } = await getT(principal.locale);

  if (principal.kind === "partner" && (await consoleVersionOf(principal)) === "v2") {
    const collapsed = (await cookies()).get(NAV_COOKIE)?.value === NAV_COLLAPSED;
    return (
      <ConsoleShellV2
        who={{ role: principal.role, modules: principal.modules }}
        user={{ name: principal.name, email: principal.email }}
        partnerName={principal.partnerName}
        defaultCollapsed={collapsed}
        // Spec 032: the Companion is a module Auphere switches on per partner.
        companion={principal.modules.includes("companion") ? <CompanionLauncher role={principal.role} userId={principal.userId} /> : null}
      >
        {children}
      </ConsoleShellV2>
    );
  }

  return (
    <ConsoleShellV1 principal={principal} skipLabel={t("shell.skip")}>
      {children}
    </ConsoleShellV1>
  );
}
