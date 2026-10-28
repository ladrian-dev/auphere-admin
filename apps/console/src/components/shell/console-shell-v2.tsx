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
import { ThemeSwitch } from "./theme-switch";

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
 *   nombre como tooltip), como el prototipo aprobado: «Operar» y «Cuenta», cada
 *   grupo con su etiqueta, seguidos, y el menú de perfil al pie.
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

  const account = nav.bottom.map((item) => ({ href: item.href, label: t(item.labelKey), icon: item.icon }));

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
            // Como el prototipo: solo se desliza el ancho; el relleno no cambia,
            // así los iconos no se mueven y los textos se desvanecen.
            "flex min-h-0 shrink-0 flex-col gap-2 overflow-hidden px-3 py-3 transition-[width] duration-(--duration-state) ease-(--ease-enter) motion-reduce:transition-none max-shell:hidden",
            collapsed ? "w-(--size-nav-collapsed)" : "w-(--size-nav)",
          )}
        >
          <div className="flex h-10 min-w-0 items-center gap-2 overflow-hidden px-1">
            <BrandLockup className="shrink-0" />
            <span
              title={t("shell.beta.hint")}
              aria-hidden={collapsed || undefined}
              className={cn(
                "shrink-0 rounded-full bg-status-warning-bg px-2 text-xs leading-5 font-semibold text-status-warning-text ring-1 ring-status-warning-border transition-opacity duration-(--duration-state) motion-reduce:transition-none",
                collapsed && "opacity-0",
              )}
            >
              {t("shell.beta")}
            </span>
          </div>
          {/* Solo «Operar»: Equipo, Facturación y API viven en el menú del perfil (Andrés, 2026-10-28). */}
          <nav aria-label={t("shell.nav.label")} className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-x-hidden overflow-y-auto pt-3">
            {nav.top.length > 0 ? (
              <NavGroup label={t("nav.group.operate")} collapsed={collapsed}>
                {nav.top.map((item) => (
                  <li key={item.href} className="min-w-0">
                    {entry(item, "sidebar")}
                  </li>
                ))}
              </NavGroup>
            ) : null}
          </nav>
          <div className="flex min-w-0">
            <ProfileMenu user={user} role={who.role} partnerName={partnerName} account={account} variant="full" collapsed={collapsed} side="top" />
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* `shell:pl-0`: el botón del menú queda a plomo con el borde del lienzo. */}
          <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 shell:pl-0">
            <BrandLockup className="shell:hidden" />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="max-shell:hidden"
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
            <ThemeSwitch />
            <NotificationsBellMenu initialUnread={null} />
            <div data-slot="shell-mobile-profile" className="shell:hidden">
              <ProfileMenu user={user} role={who.role} partnerName={partnerName} account={account} variant="avatar" side="bottom" />
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
                {nav.top.map((item) => (
                  <li key={item.href} className="shrink-0">
                    {entry(item, "bar")}
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          {/* El contenido, el único que hace scroll. */}
          <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-card max-shell:mx-2 max-shell:mb-2 shell:mr-4 shell:mb-4">
            <main
              id="main"
              tabIndex={-1}
              className="mx-auto flex w-full max-w-(--width-content) min-w-0 flex-col gap-5 px-4 pt-6 pb-12 outline-none md:px-12 md:pt-10 md:pb-16"
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

/** Un grupo del menú con su etiqueta («OPERAR», «CUENTA»); plegado, la etiqueta solo la oye el lector de pantalla. */
function NavGroup({ label, collapsed, children }: { label: string; collapsed: boolean; children: React.ReactNode }) {
  const id = React.useId();
  return (
    // `grid-cols-[minmax(0,1fr)]`: plegado, cada fila mide lo que el lateral y no
    // lo que su texto; si no, el resalte se cortaba y el nombre salía lejos.
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-2">
      <span
        id={id}
        className={cn(
          "truncate px-3 text-[11px] font-semibold tracking-[0.08em] whitespace-nowrap text-muted-foreground uppercase transition-opacity duration-(--duration-state) motion-reduce:transition-none",
          collapsed && "opacity-0",
        )}
      >
        {label}
      </span>
      <ul aria-labelledby={id} className="flex min-w-0 flex-col gap-1">
        {children}
      </ul>
    </div>
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
        // Como el prototipo: 15 px y tinta plena; el gris al pasar y el verde
        // suave solo para donde estás.
        "flex min-w-0 items-center gap-3 overflow-hidden rounded-md text-[15px] whitespace-nowrap text-sidebar-foreground transition-colors duration-(--duration-hover) hover:bg-muted",
        active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent",
        variant === "sidebar" ? "h-9 px-3" : "h-9 gap-2 px-3",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {/* Plegado, el nombre se desvanece pero sigue siendo el nombre del enlace. */}
      <span className={cn("min-w-0 truncate transition-opacity duration-(--duration-state) motion-reduce:transition-none", collapsed && "opacity-0")}>{label}</span>
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
