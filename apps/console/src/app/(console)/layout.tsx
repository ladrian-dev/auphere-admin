import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { ConsoleFrame } from "@/components/shell/console-frame";
import { clientModuleOfPath, isClientAccountPath } from "@/lib/principal-access";
import { firstModulePath, requirePrincipal } from "@/lib/principal";

/**
 * The console shell (CP-07). ``requirePrincipal`` is the real gate: an
 * anonymous visitor goes to /login, a signed-in user with no partner (or a
 * partner not yet enabled) goes to /no-access.
 *
 * Spec 047 (T004): the frame is chosen in `ConsoleFrame` (spec 056 took it out
 * of here, so the 404 is drawn in it too). A partner with the new console
 * activated gets `ConsoleShellV2`; every other partner, and every client person
 * (spec 030), gets today's (`ConsoleShellV1`), unchanged.
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
  return ConsoleFrame({ principal, children });
}
