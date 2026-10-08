import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { ClientPrincipal } from "@/lib/principal";

import { LitePanelView } from "./lite-panel-view";

/**
 * Spec 030 (US3): the Panel of one client. One call for the figures and one
 * for whom to ask about the balance; each degrades on its own.
 */
export async function LitePanel({ principal }: { principal: ClientPrincipal }) {
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const [home, me] = await Promise.all([api.liteHome().catch(() => null), api.liteMe().catch(() => null)]);
  return (
    <LitePanelView
      who={{ name: principal.name, clientName: principal.clientName, modules: principal.modules }}
      home={home}
      contact={me?.balance_contact ?? null}
      t={t}
      locale={locale}
    />
  );
}
