import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { ClientPrincipal } from "@/lib/principal";

import { LitePanelView } from "./lite-panel-view";

/**
 * Spec 030 (US3): the Panel of one client. One call for the figures and one
 * for whom to ask about the balance; each degrades on its own. Spec 043
 * (T026): with Reservas, its summary too, in parallel — a failed read is
 * `null` and the block says so, the rest of the Panel is not held up.
 */
export async function LitePanel({ principal }: { principal: ClientPrincipal }) {
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const hasReservas = principal.modules.includes("reservas");
  const [home, me, summary] = await Promise.all([
    api.liteHome().catch(() => null),
    api.liteMe().catch(() => null),
    hasReservas ? api.reservasSummary().catch(() => null) : Promise.resolve(null),
  ]);
  return (
    <LitePanelView
      who={{ name: principal.name, clientName: principal.clientName, modules: principal.modules }}
      home={home}
      contact={me?.balance_contact ?? null}
      reservas={hasReservas ? { info: me?.reservas ?? null, summary } : null}
      t={t}
      locale={locale}
    />
  );
}
