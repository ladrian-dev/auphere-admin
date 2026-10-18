import type { LucideIcon } from "lucide-react";
import {
  Activity,
  FlaskConical,
  Handshake,
  Inbox,
  LayoutDashboard,
  Phone,
  Plug,
  Store,
  UserPlus,
} from "lucide-react";

/**
 * Spec 031 (R2.1): the operator panel's navigation, ordered like Chatwoot's
 * super admin — the home on its own, then what the team manages, then the
 * platform's shared pieces, then the instance. Spanish only.
 */
export type NavItem = { href: string; label: string; icon: LucideIcon; exact?: boolean };
export type NavGroup = { id: string; label: string | null; items: NavItem[] };

export const NAV: NavGroup[] = [
  {
    id: "home",
    label: null,
    items: [{ href: "/", label: "Panel", icon: LayoutDashboard, exact: true }],
  },
  {
    id: "manage",
    label: "Gestionar",
    items: [
      { href: "/partners", label: "Partners", icon: Handshake },
      { href: "/tenants", label: "Clientes", icon: Store },
      { href: "/signups", label: "Altas", icon: UserPlus },
      { href: "/tickets", label: "Tickets", icon: Inbox },
    ],
  },
  {
    id: "platform",
    label: "Plataforma",
    items: [
      { href: "/connectors", label: "Conectores", icon: Plug },
      { href: "/auphere/channels", label: "Canales de Auphere", icon: Phone },
      { href: "/qa", label: "Playground QA", icon: FlaskConical },
    ],
  },
  {
    id: "instance",
    label: "Instancia",
    items: [{ href: "/status", label: "Estado", icon: Activity }],
  },
];

/** R2.2: a child route keeps its section lit (`/partners/x/money` → Partners). */
export function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

/** Every view of the sidebar, flat — the command palette offers them too. */
export function allNavItems(): NavItem[] {
  return NAV.flatMap((g) => g.items);
}
