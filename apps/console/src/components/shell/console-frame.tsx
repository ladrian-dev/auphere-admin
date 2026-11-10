import { cookies } from "next/headers";
import { cache } from "react";

import { CompanionLauncher } from "@/components/companion/companion-launcher";
import { ViewerKindProvider } from "@/components/error-boundary";
import { ConsoleShellV1 } from "@/components/shell/console-shell-v1";
import { ConsoleShellV2 } from "@/components/shell/console-shell-v2";
import { NAV_COLLAPSED, NAV_COOKIE, resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, type ConsoleVersion } from "@/lib/backend";
import type { PartnerPrincipal, Principal } from "@/lib/principal";

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
 * The console's frame around a screen — its menu, its bar and its bell — for
 * whoever is signed in. Spec 047 (T004): a partner with the new console
 * activated gets `ConsoleShellV2`; every other partner, and every client person
 * (spec 030), gets today's (`ConsoleShellV1`), unchanged.
 *
 * Spec 056 (14.2) takes it out of `(console)/layout.tsx` so the 404 of a route
 * that does not exist (`app/not-found.tsx`, outside the route groups) is drawn
 * inside the same console, with its menu.
 */
export async function ConsoleFrame({ principal, children }: { principal: Principal; children: React.ReactNode }) {
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
        {/* Spec 056 (10.1): the new frame is a partner's. */}
        <ViewerKindProvider kind="partner">{children}</ViewerKindProvider>
      </ConsoleShellV2>
    );
  }

  return (
    <ConsoleShellV1 principal={principal} skipLabel={t("shell.skip")}>
      {children}
    </ConsoleShellV1>
  );
}
