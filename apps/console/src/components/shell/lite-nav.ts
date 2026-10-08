import type { LucideIcon } from "lucide-react";
import { BarChart3, Inbox, LayoutDashboard } from "lucide-react";

import type { MessageKey } from "@/i18n/messages";
import type { ClientModule } from "@/lib/principal-access";

type LiteItem = { href: string; labelKey: MessageKey; icon: LucideIcon; exact?: boolean };
type LiteGroup = { labelKey: MessageKey; items: LiteItem[] };

/**
 * Spec 030: the client console's navigation. One group, the client's modules
 * in sidebar order — Panel, Bandeja de entrada, Consumo — and nothing of the
 * partner. Same hrefs as the partner console where the screen is the same
 * (`/` and `/usage`): the page decides what to paint from who is asking.
 */
const ITEMS: Record<ClientModule, LiteItem> = {
  panel: { href: "/", labelKey: "nav.home", icon: LayoutDashboard, exact: true },
  inbox: { href: "/inbox", labelKey: "nav.inbox", icon: Inbox },
  usage: { href: "/usage", labelKey: "nav.usage", icon: BarChart3 },
};
const ORDER: readonly ClientModule[] = ["panel", "inbox", "usage"];

export function liteNav(modules: readonly ClientModule[]): LiteGroup[] {
  const items = ORDER.filter((m) => modules.includes(m)).map((m) => ITEMS[m]);
  return items.length ? [{ labelKey: "nav.group.operate", items }] : [];
}
