import { ConsoleFrame } from "@/components/shell/console-frame";
import { NotFoundView } from "@/components/shell/not-found-view";
import { getT } from "@/i18n/server";
import { firstModulePath, firstPartnerModulePath, resolvePrincipal } from "@/lib/principal";

/**
 * Spec 056 (14.2 to 14.4): a route that does not exist. With a session it is
 * drawn inside the console —the same frame, with its menu— and leads to the
 * person's first module; without one, it offers «Entrar». The words go through
 * the translations and never say whether what was asked for exists.
 *
 * There is no catch-all route: a client person who types a partner's path is
 * already sent to its first module by `(console)/layout.tsx`.
 */
export default async function NotFound() {
  const resolution = await resolvePrincipal().catch(() => null);
  const principal = resolution?.kind === "ok" ? resolution.principal : null;
  const { t } = await getT(principal?.locale);
  if (!principal) {
    return (
      <main className="flex min-h-svh min-w-0 items-center justify-center">
        <NotFoundView t={t} home={null} />
      </main>
    );
  }
  const home = principal.kind === "client" ? firstModulePath(principal.modules) : firstPartnerModulePath(principal.modules);
  return ConsoleFrame({ principal, children: <NotFoundView t={t} home={home} /> });
}
