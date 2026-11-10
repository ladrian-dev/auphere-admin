import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@nexus/ui";
import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import { PARTNER_MODULES } from "@/lib/principal-access";

const nav = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/auth-actions", () => ({ signOutAction: vi.fn() }));
// El buscador y la campana tienen sus propias pruebas; aquí solo importa que
// el marco los pone, una vez cada uno.
vi.mock("../console-command-palette", () => ({
  ConsoleCommandPaletteV2: () => <button type="button">Buscar…</button>,
}));
vi.mock("../notifications-bell", () => ({
  NotificationsBellMenu: () => <button type="button">Notificaciones</button>,
}));

const { ShellBackButton } = await import("../shell-back-button");
const { ConsoleShellV2 } = await import("../console-shell-v2");
const { CrumbName } = await import("../crumb-names");

/**
 * Spec 047 (R47.1, R47.7, R47.11, R47.12): el marco común de la consola nueva.
 * - Menú lateral plegable, como el prototipo aprobado: «Operar» (Panel, Clientes,
 *   Consumo, Auditoría, Guía del partner y Teammate) y «Cuenta» (Equipo,
 *   Facturación y API), cada grupo con su etiqueta; el perfil, al pie.
 *   Plegado mide 64 px y cada entrada enseña su nombre como tooltip.
 * - Migas de pan, donde el último elemento no es un enlace.
 * - El buscador ⌘K y la campana.
 * - El menú de perfil con el tema (Claro, Oscuro o Sistema) y «Cerrar sesión».
 *   Hasta 900 px el menú pasa a una barra superior que conserva el perfil y el tema.
 */
function Shell({ collapsed = false, children }: { collapsed?: boolean; children?: React.ReactNode }) {
  return (
    <ThemeProvider>
      <LocaleProvider locale="es">
        <ConsoleShellV2
          who={{ role: "owner", modules: [...PARTNER_MODULES] }}
          user={{ name: "Luis Matos", email: "luis@ladrian.studio" }}
          partnerName="Ladrian Studio"
          defaultCollapsed={collapsed}
        >
          {children ?? <h1>Clientes</h1>}
        </ConsoleShellV2>
      </LocaleProvider>
    </ThemeProvider>
  );
}

const sidebar = () => document.querySelector<HTMLElement>("[data-slot=shell-sidebar]")!;
const mobileNav = () => document.querySelector<HTMLElement>("[data-slot=shell-mobile-nav]")!;
const linksIn = (el: HTMLElement) => within(el).getAllByRole("link").map((a) => a.textContent?.trim());

describe("ConsoleShellV2 — el marco", () => {
  beforeEach(() => {
    nav.pathname = "/";
    document.cookie = "nexus-console.nav=; path=/; max-age=0";
  });

  it("el menú lateral solo lleva «Operar»: Equipo, Facturación y API viven en el perfil (Andrés, 2026-10-28)", () => {
    render(<Shell />);
    const aside = sidebar();
    const operate = within(aside).getByRole("list", { name: "Operar" });
    expect(linksIn(operate)).toEqual(["Panel", "Clientes", "Consumo", "Auditoría", "Guía del partner", "Teammate"]);
    expect(within(aside).queryByRole("list", { name: "Cuenta" })).toBeNull();
    expect(within(aside).queryByRole("link", { name: "Facturación" })).toBeNull();
  });

  it("el botón del menú se alinea con el borde del lienzo", () => {
    render(<Shell />);
    const header = screen.getByRole("button", { name: "Plegar menú" }).closest("header")!;
    expect(header.className).toMatch(/shell:pl-0/);
    expect(screen.getByRole("button", { name: "Plegar menú" }).className).not.toMatch(/-ml-1/);
  });

  it("el tema es un interruptor junto a la campana", async () => {
    const user = userEvent.setup();
    render(<Shell />);
    const toggle = screen.getByRole("switch", { name: "Modo oscuro" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(toggle);
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.click(toggle);
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "light"));
  });

  it("un botón redondo de vidrio vuelve a la miga anterior, junto al título y no en la barra; en la portada no está", () => {
    nav.pathname = "/clients/flor/agents/a-1";
    const { unmount } = render(
      <Shell>
        <CrumbName id="flor" label="Flor y Encanto" />
        <CrumbName id="a-1" label="Recepción" />
        <ShellBackButton />
      </Shell>,
    );
    const back = screen.getByRole("link", { name: "Volver a Flor y Encanto" });
    expect(back).toHaveAttribute("href", "/clients/flor/agents");
    expect(back.className).toMatch(/(^|\s)glass(\s|$)/);
    expect(back.className).toMatch(/rounded-full/);
    // Andrés, 2026-10-28: va con el título de la página, no con las migas.
    expect(back.closest("header")).toBeNull();
    expect(back.closest("main")).not.toBeNull();
    unmount();
    nav.pathname = "/";
    render(
      <Shell>
        <ShellBackButton />
      </Shell>,
    );
    expect(screen.queryByRole("link", { name: /^Volver a/ })).toBeNull();
  });

  it("plegado, las etiquetas de grupo no se ven pero los grupos conservan su nombre", () => {
    render(<Shell collapsed />);
    expect(within(sidebar()).getByRole("list", { name: "Operar" })).toBeTruthy();
    // Se desvanece sin cambiar de sitio: el plegado no da saltos (Andrés, 2026-10-28).
    expect(within(sidebar()).getByText("Operar")).toHaveClass("opacity-0");
  });

  it("cada pantalla es un enlace con su URL, y la activa lo dice", () => {
    nav.pathname = "/clients/flor/agents/a-1";
    render(<Shell />);
    const clients = within(sidebar()).getByRole("link", { name: "Clientes" });
    expect(clients).toHaveAttribute("href", "/clients");
    expect(clients).toHaveAttribute("aria-current", "page");
    expect(within(sidebar()).getByRole("link", { name: "Panel" })).not.toHaveAttribute("aria-current");
  });

  it("se pliega a 64 px, recuerda el estado y cada entrada conserva su nombre", async () => {
    const user = userEvent.setup();
    render(<Shell />);
    const toggle = screen.getByRole("button", { name: "Plegar menú" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("aria-controls", sidebar().id);
    await user.click(toggle);
    expect(sidebar()).toHaveAttribute("data-collapsed", "true");
    expect(sidebar().className).toMatch(/w-\(--size-nav-collapsed\)/);
    expect(screen.getByRole("button", { name: "Abrir menú" })).toHaveAttribute("aria-expanded", "false");
    expect(document.cookie).toContain("nexus-console.nav=collapsed");
    // Plegado, el texto no se ve pero el enlace se sigue llamando igual.
    expect(within(sidebar()).getByRole("link", { name: "Consumo" })).toBeInTheDocument();
  });

  it("plegado, el nombre de cada entrada sale como tooltip", async () => {
    render(<Shell collapsed />);
    const usage = within(sidebar()).getByRole("link", { name: "Consumo" });
    await act(async () => {
      fireEvent.mouseEnter(usage);
      fireEvent.mouseMove(usage);
      fireEvent.focus(usage);
    });
    await waitFor(() => expect(document.querySelector("[data-slot=tooltip-content]")).toHaveTextContent("Consumo"));
  });

  it("las migas: el último elemento no es un enlace", () => {
    nav.pathname = "/clients/flor/agents/a-1";
    render(
      <Shell>
        <CrumbName id="flor" label="Flor y Encanto" />
        <CrumbName id="a-1" label="Recepción" />
      </Shell>,
    );
    const crumbs = screen.getByRole("navigation", { name: "Migas de pan" });
    expect(within(crumbs).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Clientes", "/clients"],
      ["Flor y Encanto", "/clients/flor/agents"],
    ]);
    const current = within(crumbs).getByText("Recepción");
    expect(current.closest("a")).toBeNull();
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("el buscador y la campana están una sola vez", () => {
    render(<Shell />);
    expect(screen.getAllByRole("button", { name: "Buscar…" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Notificaciones" })).toHaveLength(1);
  });

  it("el menú de perfil lleva Equipo, Facturación y API, el idioma y «Cerrar sesión»", async () => {
    const user = userEvent.setup();
    render(<Shell />);
    await user.click(within(sidebar()).getByRole("button", { name: /Luis Matos/ }));
    const menu = await screen.findByRole("menu");
    for (const [name, href] of [
      ["Equipo", "/team"],
      ["Facturación", "/billing"],
      ["API", "/keys"],
    ]) {
      expect(within(menu).getByRole("menuitem", { name })).toHaveAttribute("href", href);
    }
    // El tema ya no está aquí: es el interruptor de la barra.
    expect(within(menu).queryAllByRole("menuitemradio")).toHaveLength(0);
    expect(within(menu).getByRole("menuitem", { name: "Cerrar sesión" })).toBeInTheDocument();
  });

  it("hasta 900 px: la barra superior conserva el menú, el perfil con la cuenta y el tema", async () => {
    const user = userEvent.setup();
    render(<Shell />);
    // El lateral se oculta por CSS a ese ancho y aparece la barra (las clases
    // las decide el punto de ruptura `shell`).
    expect(sidebar().className).toMatch(/max-shell:hidden/);
    const bar = mobileNav();
    expect(bar.className).toMatch(/shell:hidden/);
    expect(linksIn(bar)).toEqual(["Panel", "Clientes", "Consumo", "Auditoría", "Guía del partner", "Teammate"]);
    // La fila de entradas se desplaza de lado dentro de su caja, sin desbordar la página.
    expect(bar.querySelector("[data-scroll-x]")).not.toBeNull();
    const profile = document.querySelector<HTMLElement>("[data-slot=shell-mobile-profile]")!;
    expect(profile.className).toMatch(/shell:hidden/);
    await user.click(within(profile).getByRole("button"));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Facturación" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Modo oscuro" })).toBeInTheDocument();
  });

  it("salta al contenido y el contenido es el `main`", () => {
    render(<Shell />);
    expect(screen.getByRole("link", { name: "Saltar al contenido" })).toHaveAttribute("href", "#main");
    expect(document.querySelector("main#main")).toHaveTextContent("Clientes");
  });

  // jsdom no aplica media queries: las dos versiones del menú (lateral y fila)
  // están a la vez en el DOM. Se esconde la que el CSS escondería a cada ancho
  // y se audita cada una; Playwright lo mide de verdad a 390 y a 1280 px.
  it("pasa axe, abierto y plegado, como escritorio y como móvil", async () => {
    const { unmount } = render(<Shell />);
    mobileNav().hidden = true;
    expect(await axeViolations(), "escritorio").toEqual([]);
    mobileNav().hidden = false;
    sidebar().hidden = true;
    expect(await axeViolations(), "móvil").toEqual([]);
    unmount();
    render(<Shell collapsed />);
    mobileNav().hidden = true;
    expect(await axeViolations(), "plegado").toEqual([]);
  });
});
