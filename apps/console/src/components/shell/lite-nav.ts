import type { LucideIcon } from "lucide-react";
import { BarChart3, CalendarDays, Inbox, LayoutDashboard } from "lucide-react";

import type { MessageKey } from "@/i18n/messages";
import type { ClientModule } from "@/lib/principal-access";

type LiteItem = { href: string; labelKey: MessageKey; icon: LucideIcon; exact?: boolean };
type LiteGroup = { labelKey: MessageKey; items: LiteItem[] };

/**
 * Spec 030: the client console's navigation. One group, the client's modules
 * in the order the API sends — Panel, Bandeja de entrada, Reservas (spec 043),
 * Consumo — and nothing of the partner. Same hrefs as the partner console where the screen is the same
 * (`/` and `/usage`): the page decides what to paint from who is asking.
 */
const ITEMS: Record<ClientModule, LiteItem> = {
  panel: { href: "/", labelKey: "nav.home", icon: LayoutDashboard, exact: true },
  inbox: { href: "/inbox", labelKey: "nav.inbox", icon: Inbox },
  reservas: { href: "/reservas", labelKey: "nav.reservas", icon: CalendarDays },
  usage: { href: "/usage", labelKey: "nav.usage", icon: BarChart3 },
};
/**
 * Spec 031 (R3.2): no order of its own. `modules` arrives in the API's order
 * (`/console/auth/session` and `/console/lite/me.nav` both come from
 * `ClientAccess.ordered_modules()`), and the bar paints it as it comes.
 */
export function liteNav(modules: readonly ClientModule[]): LiteGroup[] {
  const items = modules.map((m) => ITEMS[m]);
  return items.length ? [{ labelKey: "nav.group.operate", items }] : [];
}
