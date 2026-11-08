import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientDetailV2 } from "@/lib/backend/client-records";

const nav = vi.hoisted(() => ({ pathname: "/clients/barberia-cultor/business" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  archiveClientAction: vi.fn(),
  deleteClientV2Action: vi.fn(),
  getClientV2Action: vi.fn(),
  restoreClientAction: vi.fn(),
  updateClientV2Action: vi.fn(),
}));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { ClientHeaderV2, activeTab } = await import("../client-header-v2");
const { useCrumbNames } = await import("@/components/shell/crumb-names");

/**
 * Recorrido UI de la 047: las migas de un cliente decían su referencia
 * («Clientes › flor-y-encanto»). Con el alta en tres datos la referencia la
 * deriva la consola, no la elige el partner: la cabecera anuncia el nombre.
 */
const DETAIL: ClientDetailV2 = {
  external_client_ref: "barberia-cultor",
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  niche: "Barbería de barrio",
  info: null,
  website: null,
  country: "ES",
  price_currency: "EUR",
  wallet_currency: "USD",
  eu_only: true,
  lifecycle: "active",
  revision: 4,
  allowed: ["new_agent", "archive"],
};

function Crumbs() {
  const names = useCrumbNames();
  return <output data-testid="crumbs">{names["barberia-cultor"] ?? ""}</output>;
}

describe("ClientHeaderV2", () => {
  it("da a las migas el nombre del cliente, no su referencia", () => {
    render(
      <LocaleProvider locale="es">
        <Crumbs />
        <ClientHeaderV2 client={DETAIL} />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("crumbs").textContent).toBe("Barbería Cultor");
  });

  it("como el prototipo: nicho y desde cuándo atiende, pestañas en vidrio con los agentes y «Nuevo agente»", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} servingSince="2026-09-03T10:00:00Z" />
      </LocaleProvider>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Barbería Cultor" })).toBeVisible();
    // El botón de volver va junto al título (Andrés, 2026-10-28).
    const back = screen.getByRole("link", { name: "Volver a Clientes" });
    expect(back).toHaveAttribute("href", "/clients");
    expect(back.parentElement).toBe(screen.getByRole("heading", { level: 1 }).parentElement);
    expect(screen.getByText("Atiende desde el 3 sept 2026")).toBeVisible();
    const tabs = screen.getByRole("navigation", { name: "Secciones del cliente" });
    expect(tabs.querySelector("ul")?.className).toMatch(/(^|\s)glass(\s|$)/);
    // Sin número en la pestaña (Andrés, 2026-10-28).
    expect(screen.getByRole("link", { name: "Agentes" })).toHaveAttribute("href", "/clients/barberia-cultor/agents");
    expect(screen.getByRole("link", { name: "Nuevo agente" })).toHaveAttribute("href", "/clients/barberia-cultor/agents/new");
    // Activo, la cabecera no lleva insignia ni «⋯»: archivar y borrar están en la lista.
    expect(screen.queryByText("Activo")).toBeNull();
    expect(screen.queryByRole("button", { name: "Acciones de Barbería Cultor" })).toBeNull();
  });

  it.each([
    "/clients/barberia-cultor/agents/11111111-1111-4111-8111-111111111111",
    "/clients/barberia-cultor/agents/new",
    "/clients/barberia-cultor/agents/11111111-1111-4111-8111-111111111111/channels/22222222-2222-4222-8222-222222222222",
  ])("en la página de un agente (%s) el título es el agente: la ficha deja su cabecera, no sus migas", (pathname) => {
    nav.pathname = pathname;
    try {
      render(
        <LocaleProvider locale="es">
          <Crumbs />
          <ClientHeaderV2 client={DETAIL} />
        </LocaleProvider>,
      );
      expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
      expect(screen.queryByRole("navigation", { name: "Secciones del cliente" })).toBeNull();
      expect(screen.getByTestId("crumbs").textContent).toBe("Barbería Cultor");
    } finally {
      nav.pathname = "/clients/barberia-cultor/business";
    }
  });

  // Spec 056 (requisitos 3.1 y 3.2; D4): la pestaña «Acceso», después de Agentes,
  // solo para owner y admin. Para los demás roles no existe.
  it("con permiso, la pestaña Acceso va detrás de Agentes y tiene su dirección", () => {
    nav.pathname = "/clients/barberia-cultor/access";
    try {
      render(
        <LocaleProvider locale="es">
          <ClientHeaderV2 client={DETAIL} canManageAccess />
        </LocaleProvider>,
      );
      const tabs = screen.getByRole("navigation", { name: "Secciones del cliente" });
      const links = Array.from(tabs.querySelectorAll("a")).map((a) => a.textContent);
      expect(links).toEqual(["Panel", "Negocio", "Agentes", "Acceso"]);
      const access = screen.getByRole("link", { name: "Acceso" });
      expect(access).toHaveAttribute("href", "/clients/barberia-cultor/access");
      expect(access).toHaveAttribute("aria-current", "page");
    } finally {
      nav.pathname = "/clients/barberia-cultor/business";
    }
  });

  it("sin permiso, la pestaña Acceso no existe", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("link", { name: "Acceso" })).toBeNull();
  });

  it("la ruta /access es la pestaña Acceso", () => {
    expect(activeTab("/clients/barberia-cultor/access", "barberia-cultor")).toBe("access");
    expect(activeTab("/clients/barberia-cultor/accesses", "barberia-cultor")).toBeNull();
  });

  it("archivado lo dice y deja sus acciones; sin permiso no hay «Nuevo agente»", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={{ ...DETAIL, lifecycle: "archived", allowed: ["restore"] }} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Archivado")).toBeVisible();
    expect(screen.getByRole("button", { name: "Acciones de Barbería Cultor" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
  });
});
