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
 * Spec 083, enmienda del 2026-11-27 (T023; requisito 11.7, D22): la ficha del
 * cliente ya no tiene la pestaña «Informe». Las cifras viven en Métricas, y
 * `/clients/{ref}/report` lleva allí (prueba de `report/page.tsx`).
 */
describe("ClientHeaderV2 · sin la pestaña Informe", () => {
  it("las pestañas son las de antes de la 083, también con todos los permisos", () => {
    render(
      <LocaleProvider locale="es">
        <ClientHeaderV2 client={DETAIL} canManageAccess />
      </LocaleProvider>,
    );
    const tabs = screen.getByRole("navigation", { name: "Secciones del cliente" });
    expect(Array.from(tabs.querySelectorAll("a")).map((a) => a.textContent)).toEqual(["Panel", "Negocio", "Agentes", "Anuncios", "Acceso"]);
    expect(screen.queryByRole("link", { name: "Informe" })).toBeNull();
  });

  it("la ruta /report no es una pestaña", () => {
    expect(activeTab("/clients/barberia-cultor/report", "barberia-cultor")).toBeNull();
  });
});
