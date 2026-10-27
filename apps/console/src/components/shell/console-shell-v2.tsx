"use client";

import { Menu, PanelLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { BrandLockup, Button, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { Role } from "@/lib/permissions";
import type { PartnerModule } from "@/lib/principal-access";

import { ConsoleCommandPaletteV2 } from "./console-command-palette";
import { NAV_COLLAPSED, NAV_COOKIE } from "./console-version";
import { isActive, type NavItem } from "./nav";
import { navV2 } from "./nav-v2";
import { NotificationsBellMenu } from "./notifications-bell";
import { ProfileMenu } from "./profile-menu";
import { ShellBreadcrumbs } from "./shell-breadcrumbs";

type Props = {
  who: { role: Role; modules: PartnerModule[] };
  user: { name: string; email: string };
  partnerName: string;
  /** Lo que el `layout` leyó de la cookie: así el menú se pinta plegado sin salto. */
  defaultCollapsed?: boolean;
  /** El Companion, si Auphere se lo dio al partner (spec 032). */
  companion?: React.ReactNode;
  children: React.ReactNode;
};

/**
 * Spec 047 (R47.1, R47.7, R47.11, R47.12) — el marco de la consola nueva.
 *
 * - Desde 901 px: el menú lateral, plegable a 64 px (cada entrada enseña su
 *   nombre como tooltip), sin etiquetas de grupo; lo de operar arriba y lo de
 *   la cuenta abajo, con el menú de perfil al pie.
 * - Hasta 900 px: el menú pasa a una barra superior con las entradas en una
 *   fila que se desplaza de lado, y el menú de perfil (con el tema) se queda
 *   en la barra. El prototipo lo escondía en móvil (`01` §10); aquí no.
 * - Arriba, siempre: las migas, el buscador ⌘K y la campana, una vez cada uno.
 * - Cada entrada es un enlace: cada pantalla tiene su URL y el botón atrás del
 *   navegador vuelve a la anterior.
 * - Solo el contenido hace scroll; el marco mide la ventana.
 */
export function ConsoleShellV2({ who, user, partnerName, defaultCollapsed = false, companion, children }: Props) {
  const t = useT();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(defaultCollapsed);
  const [mobileOpen, setMobileOpen] = React.useState(true);
  const sidebarId = React.useId();
  const mobileNavId = React.useId();
  const nav = navV2(who.role, who.modules);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    document.cookie = `${NAV_COOKIE}=${next ? NAV_COLLAPSED : "open"}; path=/; max-age=31536000; samesite=lax`;
  }

  const entry = (item: NavItem, variant: "sidebar" | "bar") => (
    <NavEntry key={item.href} item={item} label={t(item.labelKey)} active={isActive(pathname, item)} collapsed={variant === "sidebar" && collapsed} variant={variant} />
  );

  return (
    <TooltipProvider>
      <div data-shell="v2" className="flex h-svh min-h-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground shell:flex-row">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-(--z-toast) focus:rounded-sm focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          {t("shell.skip")}
        </a>

        {/* El menú lateral (desde 901 px). */}
        <div
          id={sidebarId}
          data-slot="shell-sidebar"
          data-collapsed={collapsed}
          className={cn(
            "flex min-h-0 shrink-0 flex-col gap-2 overflow-hidden py-3 transition-[width] duration-(--duration-state) ease-(--ease-in-out) motion-reduce:transition-none max-shell:hidden",
            collapsed ? "w-(--size-nav-collapsed) px-2" : "w-(--size-nav) px-3",
          )}
        >
          <div className={cn("flex h-10 min-w-0 items-center gap-2 overflow-hidden", collapsed ? "justify-center" : "px-2")}>
            <BrandLockup markOnly={collapsed} />
            {!collapsed ? (
              <span
                title={t("shell.beta.hint")}
                className="shrink-0 rounded-full bg-status-warning-bg px-2 text-xs leading-5 font-semibold text-status-warning-text ring-1 ring-status-warning-border"
              >
                {t("shell.beta")}
              </span>
            ) : null}
          </div>
          <nav aria-label={t("shell.nav.label")} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
            <ul className="flex flex-col gap-1">{nav.top.map((item) => <li key={item.href}>{entry(item, "sidebar")}</li>)}</ul>
            <div className="flex-1" />
            {nav.bottom.length > 0 ? (
              <ul className="flex flex-col gap-1">{nav.bottom.map((item) => <li key={item.href}>{entry(item, "sidebar")}</li>)}</ul>
            ) : null}
          </nav>
          <div className={cn("flex min-w-0", collapsed && "justify-center")}>
            <ProfileMenu user={user} role={who.role} partnerName={partnerName} variant={collapsed ? "avatar" : "full"} side="top" />
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex min-h-12 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2">
            <BrandLockup className="shell:hidden" />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="-ml-1 max-shell:hidden"
              aria-controls={sidebarId}
              aria-expanded={!collapsed}
              aria-label={t(collapsed ? "shell.nav.expand" : "shell.nav.collapse")}
              onClick={toggleSidebar}
            >
              <PanelLeft className="size-4" aria-hidden="true" />
            </Button>
            <ShellBreadcrumbs className="max-shell:order-last max-shell:w-full" />
            <div className="flex-1" />
            <ConsoleCommandPaletteV2 />
            <NotificationsBellMenu initialUnread={null} />
            <div data-slot="shell-mobile-profile" className="shell:hidden">
              <ProfileMenu user={user} role={who.role} partnerName={partnerName} variant="avatar" side="bottom" />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="shell:hidden"
              aria-controls={mobileNavId}
              aria-expanded={mobileOpen}
              aria-label={t(mobileOpen ? "shell.nav.mobile.hide" : "shell.nav.mobile.show")}
              onClick={() => setMobileOpen((o) => !o)}
            >
              <Menu className="size-4" aria-hidden="true" />
            </Button>
          </header>

          {/* El menú en una fila (hasta 900 px): se desplaza de lado dentro de su caja. */}
          <nav
            id={mobileNavId}
            data-slot="shell-mobile-nav"
            aria-label={t("shell.nav.label")}
            hidden={!mobileOpen}
            className="shrink-0 px-2 pb-2 shell:hidden"
          >
            <div data-scroll-x="" className="overflow-x-auto overscroll-x-contain">
              <ul className="flex w-max gap-1">
                {[...nav.top, ...nav.bottom].map((item) => (
                  <li key={item.href} className="shrink-0">
                    {entry(item, "bar")}
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          {/* El contenido, el único que hace scroll. */}
          <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-card max-shell:mx-2 max-shell:mb-2 shell:mr-2 shell:mb-2">
            <main
              id="main"
              tabIndex={-1}
              className="mx-auto flex w-full max-w-(--width-content) min-w-0 flex-col gap-6 px-4 py-6 outline-none md:px-8 md:py-8"
            >
              {children}
            </main>
          </div>
        </div>
        {companion}
      </div>
    </TooltipProvider>
  );
}

function NavEntry({
  item,
  label,
  active,
  collapsed,
  variant,
}: {
  item: NavItem;
  label: string;
  active: boolean;
  collapsed: boolean;
  variant: "sidebar" | "bar";
}) {
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-w-0 items-center gap-3 rounded-md text-sm font-medium text-sidebar-foreground/80 transition-colors duration-(--duration-hover) hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        active && "bg-sidebar-accent text-sidebar-accent-foreground",
        variant === "sidebar" ? "h-10 px-3" : "h-9 gap-2 px-3 whitespace-nowrap",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <span className={cn("min-w-0 truncate", collapsed && "sr-only")}>{label}</span>
    </Link>
  );
  if (variant === "bar") return link;
  // Plegado, el nombre no se ve: sale como tooltip al pasar o al enfocar.
  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger render={link} />
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
