import type { LucideIcon } from "lucide-react";
import { BarChart3, BookOpen, Building2, KeyRound, Laptop, LayoutDashboard, Receipt, ScrollText, Users } from "lucide-react";

import type { MessageKey } from "@/i18n/messages";
import { can, type Permission, type Role } from "@/lib/permissions";
import { PARTNER_MODULES, type ClientModule, type PartnerModule } from "@/lib/principal-access";

import { liteNav } from "./lite-nav";

export type NavItem = {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  permission?: Permission;
  exact?: boolean;
  /** Spec 032: the module Auphere must have switched on for this partner. */
  module?: PartnerModule;
};
export type NavGroup = { labelKey: MessageKey; items: NavItem[] };

/** Grouped, role-filtered navigation. Max depth to any view: 3 clicks. */
export const NAV: NavGroup[] = [
  {
    labelKey: "nav.group.operate",
    items: [
      // Owner's order, 2026-10-03: the dashboard, the clients and their money
      // first, then the record of what happened, the guide and the Teammate.
      { href: "/", labelKey: "nav.home", icon: LayoutDashboard, exact: true, module: "panel" },
      { href: "/clients", labelKey: "nav.clients", icon: Building2, permission: "clients:read", module: "clients" },
      { href: "/usage", labelKey: "nav.usage", icon: BarChart3, permission: "usage:read", module: "usage" },
      { href: "/audit", labelKey: "nav.audit", icon: ScrollText, permission: "audit:read", module: "audit" },
      { href: "/knowledge", labelKey: "nav.knowledge", icon: BookOpen, permission: "playbook:read", module: "knowledge" },
      { href: "/workstation", labelKey: "nav.workstation", icon: Laptop, permission: "workstation:read", module: "workstation" },
      // Notifications are reached from the bell in the top bar (owner, 2026-09-23): one place, not two.
    ],
  },
  {
    labelKey: "nav.group.account",
    items: [
      { href: "/team", labelKey: "nav.team", icon: Users, permission: "team:read", module: "team" },
      { href: "/billing", labelKey: "nav.billing", icon: Receipt, permission: "billing:read", module: "billing" },
      { href: "/keys", labelKey: "nav.keys", icon: KeyRound, permission: "keys:read", module: "keys" },
    ],
  },
];

/** Spec 032: what a partner member sees — the modules Auphere gave the
 * partner AND the permissions of the person's role. */
export function navForPartner(role: Role, modules: readonly PartnerModule[]): NavGroup[] {
  return NAV.map((g) => ({
    ...g,
    items: g.items.filter(
      (i) => (!i.module || modules.includes(i.module)) && (!i.permission || can(role, i.permission)),
    ),
  })).filter((g) => g.items.length > 0);
}

/** Every module on: what a role sees in a partner with the whole console. */
export function navForRole(role: Role): NavGroup[] {
  return navForPartner(role, PARTNER_MODULES);
}

export function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export type NavWho =
  | { kind: "partner"; role: Role; modules: readonly PartnerModule[] }
  | { kind: "client"; modules: readonly ClientModule[] };

/**
 * Spec 030: the navigation of whoever is signed in. A partner member gets the
 * partner's (above); a client user gets its client's modules (`lite-nav.ts`,
 * kept apart so this file stays exactly the partner's — the desktop app
 * reads it for its own parity test).
 */
export function navForPrincipal(who: NavWho): NavGroup[] {
  return who.kind === "partner" ? navForPartner(who.role, who.modules) : liteNav(who.modules);
}
