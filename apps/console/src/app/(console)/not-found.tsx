import { NotFoundView } from "@/components/shell/not-found-view";
import { getT } from "@/i18n/server";
import { firstModulePath, firstPartnerModulePath, requirePrincipal } from "@/lib/principal";

/**
 * Spec 056 (14.2, 14.4): a `notFound()` inside the console. The menu is already
 * there (the layout drew it): this only says it, without saying whether what was
 * asked for exists, and leads to the person's first module.
 */
export default async function ConsoleNotFound() {
  const principal = await requirePrincipal();
  const { t } = await getT(principal.locale);
  const home = principal.kind === "client" ? firstModulePath(principal.modules) : firstPartnerModulePath(principal.modules);
  return <NotFoundView t={t} home={home} />;
}
