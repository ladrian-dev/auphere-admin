import type { LucideIcon } from "lucide-react";
import { BarChart3, BookOpen, Building2, KeyRound, Laptop, LayoutDashboard, Receipt, ScrollText, Users } from "lucide-react";

import type { MessageKey } from "@/i18n/messages";
import { can, type Permission, type Role } from "@/lib/permissions";
import type { ClientModule } from "@/lib/principal-access";

import { liteNav } from "./lite-nav";

export type NavItem = { href: string; labelKey: MessageKey; icon: LucideIcon; permission?: Permission; exact?: boolean };
export type NavGroup = { labelKey: MessageKey; items: NavItem[] };

/** Grouped, role-filtered navigation. Max depth to any view: 3 clicks. */
export const NAV: NavGroup[] = [
  {
    labelKey: "nav.group.operate",
    items: [
      // Owner's order, 2026-10-03: the dashboard, the clients and their money
      // first, then the record of what happened, the guide and the Teammate.
      { href: "/", labelKey: "nav.home", icon: LayoutDashboard, exact: true },
      { href: "/clients", labelKey: "nav.clients", icon: Building2, permission: "clients:read" },
      { href: "/usage", labelKey: "nav.usage", icon: BarChart3, permission: "usage:read" },
      { href: "/audit", labelKey: "nav.audit", icon: ScrollText, permission: "audit:read" },
      { href: "/knowledge", labelKey: "nav.knowledge", icon: BookOpen, permission: "playbook:read" },
      { href: "/workstation", labelKey: "nav.workstation", icon: Laptop, permission: "workstation:read" },
      // Notifications are reached from the bell in the top bar (owner, 2026-09-23): one place, not two.
    ],
  },
  {
    labelKey: "nav.group.account",
    items: [
      { href: "/team", labelKey: "nav.team", icon: Users, permission: "team:read" },
      { href: "/billing", labelKey: "nav.billing", icon: Receipt, permission: "billing:read" },
      { href: "/keys", labelKey: "nav.keys", icon: KeyRound, permission: "keys:read" },
    ],
  },
];

export function navForRole(role: Role): NavGroup[] {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.permission || can(role, i.permission)) })).filter(
    (g) => g.items.length > 0,
  );
}

export function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export type NavWho = { kind: "partner"; role: Role } | { kind: "client"; modules: readonly ClientModule[] };

/**
 * Spec 030: the navigation of whoever is signed in. A partner member gets the
 * partner's (above); a client user gets its client's modules (`lite-nav.ts`,
 * kept apart so this file stays exactly the partner's — the desktop app
 * reads it for its own parity test).
 */
export function navForPrincipal(who: NavWho): NavGroup[] {
  return who.kind === "partner" ? navForRole(who.role) : liteNav(who.modules);
}
