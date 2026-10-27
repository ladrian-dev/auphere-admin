import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Basics, Hours, Locations, Services, SpecialDates } from "@/lib/backend/business-sections";

vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  saveHoursAction: vi.fn(),
  loadHoursAction: vi.fn(),
  saveBasicsAction: vi.fn(),
  createLocationAction: vi.fn(),
  updateLocationAction: vi.fn(),
  archiveLocationAction: vi.fn(),
  createSpecialDateAction: vi.fn(),
  archiveSpecialDateAction: vi.fn(),
  createServiceAction: vi.fn(),
  updateServiceAction: vi.fn(),
  archiveServiceAction: vi.fn(),
  duplicateServiceAction: vi.fn(),
  setServiceAgentsAction: vi.fn(),
}));

const { BusinessSectionsView } = await import("../business-sections");

/**
 * Spec 047 (T060, requisito 8.5) — la página Negocio: el índice de secciones, el
 * estado de cada una («Completa», «Leída · revísala», «Pendiente», «Opcional») y
 * los cinco estados: vacío, error, parcial (una sección no carga y las demás sí),
 * ideal; el de carga es `loading.tsx`. Y los textos largos no rompen nada.
 */

const meta = { allowed: ["edit" as const] };
const BASICS: Basics = {
  ...meta,
  revision: 1,
  state: "complete",
  name: "Barbería Cultor",
  niche: "Barbería de barrio",
  info: null,
  website: "https://cultorbarber.com",
  country: "ES",
  timezone: "Europe/Madrid",
  price_currency: "EUR",
  eu_only: true,
};
const EMPTY_DAYS = { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };
const HOURS: Hours = { ...meta, revision: 0, state: "pending", location_id: null, inherits: false, layout: null, days: EMPTY_DAYS, label: null };
const LOCATIONS: Locations = { ...meta, revision: 0, state: "pending", items: [], created_id: null };
const SPECIAL: SpecialDates = { ...meta, revision: 0, state: "optional", items: [], created_id: null };
const SERVICES: Services = { ...meta, revision: 0, state: "read_pending", currency: "EUR", exponent: 2, items: [], agents: [], created_id: null };

const ok = <T,>(data: T) => ({ ok: true as const, data });
const failed = { ok: false as const, status: 503, message: "down" };

function page(over: Partial<React.ComponentProps<typeof BusinessSectionsView>["data"]> = {}, canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <BusinessSectionsView
        refId="barberia-cultor"
        canWrite={canWrite}
        data={{
          basics: ok(BASICS),
          locations: ok(LOCATIONS),
          hours: ok(HOURS),
          specialDates: ok(SPECIAL),
          services: ok(SERVICES),
          ...over,
        }}
      />
    </LocaleProvider>,
  );
}

describe("BusinessSectionsView", () => {
  it("shows every section with its state, and an index to jump to each", async () => {
    const { container } = page();
    const index = screen.getByRole("navigation", { name: "Secciones de Negocio" });
    for (const name of ["Datos básicos", "Sedes", "Horario", "Fechas especiales", "Servicios"]) {
      expect(within(index).getByRole("link", { name: new RegExp(name) })).toBeVisible();
      expect(screen.getByRole("region", { name })).toBeVisible();
    }
    expect(within(screen.getByRole("region", { name: "Datos básicos" })).getByText("Completa")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Horario" })).getByText("Pendiente")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Fechas especiales" })).getByText("Opcional")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Servicios" })).getByText("Leída · revísala")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("empty: each section says what is missing and what the agent will do", () => {
    page();
    expect(screen.getByText(/Sin sedes\. El agente no dará ninguna dirección/)).toBeVisible();
    expect(screen.getByText(/el agente dirá que no lo sabe/)).toBeVisible();
    expect(screen.getByText(/Todavía no hay servicios/)).toBeVisible();
  });

  it("partial: a section that did not load says so; the rest still work", async () => {
    const user = userEvent.setup();
    page({ services: failed });
    const services = screen.getByRole("region", { name: "Servicios" });
    expect(within(services).getByText("No se pudo cargar esta sección.")).toBeVisible();
    expect(within(services).getByRole("button", { name: "Reintentar" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Horario" })).toBeVisible();
    await user.click(within(services).getByRole("button", { name: "Reintentar" }));
  });

  it("error: nothing loaded", () => {
    page({ basics: failed, locations: failed, hours: failed, specialDates: failed, services: failed });
    expect(screen.getAllByText("No se pudo cargar esta sección.")).toHaveLength(5);
  });

  it("long texts wrap instead of overflowing", () => {
    const long = "Peluquería y barbería de barrio con dos sedes y cafetería ".repeat(3);
    page({ basics: ok({ ...BASICS, name: long, niche: long.slice(0, 80) }) });
    const region = screen.getByRole("region", { name: "Datos básicos" });
    expect(region.className).toMatch(/min-w-0/);
  });

  it("read-only without permission", () => {
    page({}, false);
    expect(screen.queryByRole("button", { name: /^Guardar/ })).toBeNull();
    expect(screen.getAllByText("Solo lectura").length).toBeGreaterThan(0);
  });
});
