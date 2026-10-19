import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ChartColumn,
  FlaskConical,
  Handshake,
  MessagesSquare,
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
      // Spec 038: what every partner and client consumed.
      { href: "/usage", label: "Consumo", icon: ChartColumn },
      { href: "/signups", label: "Altas", icon: UserPlus },
      { href: "/tickets", label: "Tickets", icon: Inbox },
    ],
  },
  {
    id: "platform",
    label: "Plataforma",
    items: [
      // Spec 035: Canales (mensajería) and Conectores (otras apps) apart, as
      // Chatwoot keeps Inboxes and Integrations apart.
      { href: "/channels", label: "Canales", icon: MessagesSquare },
      { href: "/connectors", label: "Conectores", icon: Plug },
      { href: "/auphere/channels", label: "Números de Auphere", icon: Phone },
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
