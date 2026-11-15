import type { LucideIcon } from "lucide-react";

import { ROUTER_PANEL_VISIBLE } from "@/lib/router-panel";
import {
  Activity,
  BadgeCheck,
  ChartColumn,
  Cpu,
  FlaskConical,
  Hammer,
  Handshake,
  MessagesSquare,
  Inbox,
  LayoutDashboard,
  Phone,
  Plug,
  Route,
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

/** The routes that only make sense with the router deciding (spec 059, requisito 2). */
const ROUTER_ROUTES = new Set(["/router", "/certifications"]);

const ALL: NavGroup[] = [
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
      // Spec 047 (T150, historia 30): the model catalog, the router's policy
      // and the certifications, without touching the database. Router and
      // Certificaciones are parked by spec 059 (`navFor`).
      { href: "/models", label: "Modelos", icon: Cpu },
      { href: "/router", label: "Router", icon: Route },
      { href: "/certifications", label: "Certificaciones", icon: BadgeCheck },
      // Spec 047 (T087, T090, T100, T201): the quality of the agent builder —
      // the sector tests, the judge's calibration, the builder's evaluation
      // and the sectors without an Auphere guide.
      { href: "/builder", label: "Constructor", icon: Hammer },
    ],
  },
  {
    id: "instance",
    label: "Instancia",
    items: [{ href: "/status", label: "Estado", icon: Activity }],
  },
];

/**
 * The sidebar for a value of the router setting: parked, without Router and
 * Certificaciones; visible, exactly as spec 047 left it. Pure, so both values
 * are tested.
 */
export function navFor(routerVisible: boolean): NavGroup[] {
  if (routerVisible) return ALL;
  return ALL.map((g) => ({ ...g, items: g.items.filter((i) => !ROUTER_ROUTES.has(i.href)) }));
}

export const NAV: NavGroup[] = navFor(ROUTER_PANEL_VISIBLE);

/** R2.2: a child route keeps its section lit (`/partners/x/money` → Partners). */
export function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

/** Every view of the sidebar, flat — the command palette offers them too. */
export function allNavItems(): NavItem[] {
  return NAV.flatMap((g) => g.items);
}
