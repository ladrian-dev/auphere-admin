import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientDetailV2 } from "@/lib/backend/client-records";

const nav = vi.hoisted(() => ({ pathname: "/clients/barberia-cultor/report" }));
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

/**
 * Spec 083 (T007; requisitos 1.1 y 1.6, D1): la pestaña «Informe» va después de
 * «Anuncios» y solo existe para quien puede leer conversaciones y consumo.
 */
describe("ClientHeaderV2 · la pestaña Informe", () => {
  it("con los dos permisos, va después de Anuncios, con su dirección", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} canReadReport canManageAccess />
      </LocaleProvider>,
    );
    const tabs = screen.getByRole("navigation", { name: "Secciones del cliente" });
    expect(Array.from(tabs.querySelectorAll("a")).map((a) => a.textContent)).toEqual(["Panel", "Negocio", "Agentes", "Anuncios", "Informe", "Acceso"]);
    const report = screen.getByRole("link", { name: "Informe" });
    expect(report).toHaveAttribute("href", "/clients/barberia-cultor/report");
    expect(report).toHaveAttribute("aria-current", "page");
  });

  it("sin ellos, no existe", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("link", { name: "Informe" })).toBeNull();
  });

  it("la ruta /report es la pestaña Informe", () => {
    expect(activeTab("/clients/barberia-cultor/report", "barberia-cultor")).toBe("report");
    expect(activeTab("/clients/barberia-cultor/reports", "barberia-cultor")).toBeNull();
  });

  it("la cabecera del cliente no sale al imprimir: el informe lleva la suya", () => {
    const { container } = render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} canReadReport />
      </LocaleProvider>,
    );
    expect(container.querySelector("[data-slot=client-header-v2]")!.className).toMatch(/print:hidden/);
  });
});
