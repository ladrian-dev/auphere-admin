import type { LucideIcon } from "lucide-react";
import { BarChart3, Bell, BookOpen, Building2, KeyRound, LayoutDashboard, Receipt, ScrollText, Users } from "lucide-react";

import type { MessageKey } from "@/i18n/messages";
import { can, type Permission, type Role } from "@/lib/permissions";

export type NavItem = { href: string; labelKey: MessageKey; icon: LucideIcon; permission?: Permission; exact?: boolean };
export type NavGroup = { labelKey: MessageKey; items: NavItem[] };

/** Grouped, role-filtered navigation. Max depth to any view: 3 clicks. */
export const NAV: NavGroup[] = [
  {
    labelKey: "nav.group.operate",
    items: [
      { href: "/", labelKey: "nav.home", icon: LayoutDashboard, exact: true },
      { href: "/clients", labelKey: "nav.clients", icon: Building2, permission: "clients:read" },
      { href: "/knowledge", labelKey: "nav.knowledge", icon: BookOpen, permission: "playbook:read" },
      { href: "/usage", labelKey: "nav.usage", icon: BarChart3, permission: "usage:read" },
      { href: "/audit", labelKey: "nav.audit", icon: ScrollText, permission: "audit:read" },
      { href: "/notifications", labelKey: "nav.notifications", icon: Bell, permission: "partner:read" },
    ],
  },
  {
    labelKey: "nav.group.account",
    items: [
      { href: "/team", labelKey: "nav.team", icon: Users, permission: "team:read" },
      { href: "/keys", labelKey: "nav.keys", icon: KeyRound, permission: "keys:read" },
      { href: "/billing", labelKey: "nav.billing", icon: Receipt, permission: "billing:read" },
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
