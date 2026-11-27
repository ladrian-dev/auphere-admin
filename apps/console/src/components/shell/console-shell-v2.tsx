"use client";

import { PanelLeft } from "lucide-react";
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
import { navV2, splitForPhone } from "./nav-v2";
import { NotificationsBellMenu } from "./notifications-bell";
import { ProfileMenu } from "./profile-menu";
import { ShellBreadcrumbs } from "./shell-breadcrumbs";
import { SlidingLens } from "./sliding-lens";
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
 *   nombre como tooltip), solo con el grupo «Operar» y su etiqueta, y el menú
 *   de perfil al pie. Equipo, Facturación y API viven en ese menú de perfil
 *   (Andrés, 2026-10-28).
 * - Hasta 900 px — spec 074 (D1, owner 2026-11-22): **una sola navegación**, la
 *   barra inferior con las secciones de «Operar» y la lente de vidrio, a mano
 *   del pulgar, como la app móvil. Sin la fila de arriba ni el botón ☰. El menú
 *   de perfil (con la cuenta) se queda arriba, y en él va el tema (D2).
 * - Arriba, siempre: las migas, el buscador ⌘K, la campana y, desde 901 px, el
 *   interruptor del tema; una vez cada uno.
 * - Cada entrada es un enlace: cada pantalla tiene su URL y el botón atrás del
 *   navegador vuelve a la anterior.
 * - Solo el contenido hace scroll; el marco mide la ventana.
 */
export function ConsoleShellV2({ who, user, partnerName, defaultCollapsed = false, companion, children }: Props) {
  const t = useT();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(defaultCollapsed);
  const sidebarId = React.useId();
  const nav = navV2(who.role, who.modules);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    document.cookie = `${NAV_COOKIE}=${next ? NAV_COLLAPSED : "open"}; path=/; max-age=31536000; samesite=lax`;
  }

  const account = nav.bottom.map((item) => ({ href: item.href, label: t(item.labelKey), icon: item.icon }));
  const phone = splitForPhone(nav.top);
  const more = phone.more.map((item) => ({ href: item.href, label: t(item.labelKey), icon: item.icon }));

  const entry = (item: NavItem, variant: "sidebar" | "bar") => (
    <NavEntry key={item.href} item={item} label={t(item.labelKey)} active={isActive(pathname, item)} collapsed={variant === "sidebar" && collapsed} variant={variant} />
  );

  return (
    <TooltipProvider>
      {/* `relative` aquí y en el lienzo: sin un padre posicionado, lo que es
          `absolute` (los `sr-only` de las gráficas y las tablas) se coloca contra
          el documento, lo alarga y todo el marco subía con la rueda.
          Al imprimir (spec 083, informe del cliente) el marco se suelta: sin alto
          fijo ni desplazamiento, solo el contenido, sin menú, cabecera ni barra. */}
      <div data-shell="v2" className="relative flex h-svh min-h-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground shell:flex-row print:block print:h-auto print:overflow-visible print:bg-background print:text-foreground">
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
            "flex min-h-0 shrink-0 flex-col gap-2 overflow-hidden px-3 py-3 transition-[width] duration-(--duration-state) ease-(--ease-enter) motion-reduce:transition-none max-shell:hidden print:hidden",
            collapsed ? "w-(--size-nav-collapsed)" : "w-(--size-nav)",
          )}
        >
          <div className="flex h-10 min-w-0 items-center gap-2 overflow-hidden px-1">
            <BrandLockup className="shrink-0" />
            <span
              title={t("shell.beta.hint")}
              aria-hidden={collapsed || undefined}
              className={cn(
                // Spec 070: neutro. El ámbar es de los avisos y esto no avisa de nada.
                "shrink-0 rounded-full bg-muted px-2 text-xs leading-5 font-medium text-muted-foreground ring-1 ring-border transition-opacity duration-(--duration-state) motion-reduce:transition-none",
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

        <div className="flex min-h-0 min-w-0 flex-1 flex-col print:block">
          {/* `shell:pl-0`: el botón del menú queda a plomo con el borde del lienzo. */}
          <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 shell:pl-0 print:hidden">
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
            <ThemeSwitch className="max-shell:hidden" />
            <NotificationsBellMenu initialUnread={null} />
            <div data-slot="shell-mobile-profile" className="shell:hidden">
              <ProfileMenu user={user} role={who.role} partnerName={partnerName} account={account} variant="avatar" side="bottom" theme more={more} />
            </div>
          </header>

          {/* El contenido, el único que hace scroll. */}
          <div data-slot="shell-canvas" className="relative min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-card max-shell:mx-2 max-shell:mb-2 shell:mr-4 shell:mb-4 print:m-0 print:overflow-visible print:rounded-none print:border-0">
            <main
              id="main"
              tabIndex={-1}
              className="mx-auto flex w-full max-w-(--width-content) min-w-0 flex-col gap-5 px-4 pt-6 pb-12 outline-none md:px-12 md:pt-10 md:pb-16 print:max-w-none print:p-0"
            >
              {children}
            </main>
          </div>

          {/* Spec 074 (D1): hasta 900 px, la barra inferior es la única navegación. */}
          <nav data-slot="shell-tabbar" aria-label={t("shell.nav.label")} className="shrink-0 px-3 pt-1 shell:hidden print:hidden" style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}>
            <div className="glass relative rounded-full p-1 ring-1 ring-foreground/10">
              {/* La lente, hermana de la lista (dentro de un `ul` solo van `li`). */}
              <SlidingLens selector='[aria-current="page"]' variant="tabs" />
              <ul className="grid auto-cols-fr grid-flow-col gap-1">
                {phone.tabbar.map((item) => (
                  <li key={item.href} className="min-w-0">
                    {entry(item, "bar")}
                  </li>
                ))}
              </ul>
            </div>
          </nav>
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
      {/* Spec 070: la lente de vidrio va bajo el activo y viaja con él. */}
      <div className="relative min-w-0">
        <SlidingLens selector='[aria-current="page"]' variant="sidebar" />
        <ul aria-labelledby={id} className="flex min-w-0 flex-col gap-1">
          {children}
        </ul>
      </div>
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
        // Spec 070: 14 px (la escala compacta) y tinta plena; el gris al pasar.
        // Donde estás lo marca la lente de vidrio; el verde suave queda debajo
        // solo hasta que la lente se coloca.
        "flex min-w-0 items-center gap-3 overflow-hidden rounded-md text-[14px] whitespace-nowrap text-sidebar-foreground transition-colors duration-(--duration-hover) hover:bg-muted",
        active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent",
        // La barra inferior: icono sobre el nombre, 48 px de alto (objetivo táctil ≥ 44).
        variant === "sidebar" ? "h-9 px-3" : "h-12 flex-col justify-center gap-1 rounded-full px-1 text-[11px]",
      )}
    >
      <Icon className={cn("shrink-0", variant === "sidebar" ? "size-4" : "size-5")} aria-hidden="true" />
      {/* Plegado, el nombre se desvanece pero sigue siendo el nombre del enlace. */}
      <span className={cn("max-w-full min-w-0 truncate transition-opacity duration-(--duration-state) motion-reduce:transition-none", collapsed && "opacity-0")}>{label}</span>
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
