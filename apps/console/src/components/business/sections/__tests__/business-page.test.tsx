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
  // «Reintentar» de una sección que no cargó: vuelve a leer solo esa.
  reloadSectionAction: vi.fn(async () => ({ ok: false })),
}));
const confirmSection = vi.hoisted(() => vi.fn(async () => ({ ok: true, data: { confirmed: 1 } })));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  confirmSectionAction: confirmSection,
  putLinksAction: vi.fn(),
  listSourcesAction: vi.fn(async () => ({ ok: true, data: { items: [], removed: [], max_bytes: 10_000_000, allowed: ["add"] } })),
  uploadSourceAction: vi.fn(),
  addSourceUrlAction: vi.fn(),
  rereadSourceAction: vi.fn(),
  removeSourceAction: vi.fn(),
  restoreSourceAction: vi.fn(),
}));

const { BusinessSectionsView } = await import("../business-sections");

/**
 * Spec 047 (T060, requisito 8.5) — la página Negocio, como el prototipo aprobado
 * («Consola de partners v2»): el índice con un círculo por sección, cada sección
 * en lectura con su «Editar», solo dos marcas («Leído de la web · revísalo»,
 * con «Es correcto», y «Falta»), una sola edición a la vez, y los cinco estados:
 * vacío, error, parcial, ideal (el de carga es `loading.tsx`).
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
  it("shows every section with its mark, and an index to jump to each", async () => {
    const { container } = page();
    const index = screen.getByRole("navigation", { name: "Secciones de Negocio" });
    for (const name of ["Datos básicos", "Sedes", "Horarios", "Servicios"]) {
      expect(within(index).getByRole("link", { name: new RegExp(name) })).toBeVisible();
      expect(screen.getByRole("region", { name })).toBeVisible();
    }
    // El índice dice el estado con un círculo (y su nombre para los lectores de pantalla).
    expect(within(index).getByRole("link", { name: /Datos básicos.*Completa/ })).toBeVisible();
    expect(within(index).getByRole("link", { name: /Servicios.*Leída · revísala/ })).toBeVisible();
    // En la tarjeta, solo lo que pide algo: «Falta» y «Leído de la web · revísalo».
    expect(within(screen.getByRole("region", { name: "Datos básicos" })).queryByText("Completa")).toBeNull();
    expect(within(screen.getByRole("region", { name: "Horarios" })).getByText("Falta")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Servicios" })).getByText("Leído de la web · revísalo")).toBeVisible();
    // Las fechas especiales viven dentro de Horarios.
    expect(screen.getByRole("region", { name: "Fechas especiales" }).closest("#business-hours")).not.toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("each section is read first, «Editar» opens it, and only one is open at a time", async () => {
    const user = userEvent.setup();
    page();
    const basics = screen.getByRole("region", { name: "Datos básicos" });
    expect(within(basics).getByText("Barbería Cultor")).toBeVisible();
    expect(within(basics).queryByRole("textbox")).toBeNull();
    await user.click(within(basics).getByRole("button", { name: "Editar Datos básicos" }));
    expect(within(basics).getByRole("textbox", { name: /Nombre/ })).toHaveValue("Barbería Cultor");
    const hours = screen.getByRole("region", { name: "Horarios" });
    await user.click(within(hours).getByRole("button", { name: "Editar Horarios" }));
    // Abrir otra cierra la anterior sin guardar.
    expect(within(basics).queryByRole("textbox")).toBeNull();
    expect(within(hours).getByRole("button", { name: "Guardar horario" })).toBeVisible();
    await user.click(within(hours).getByRole("button", { name: "Cancelar" }));
    expect(within(hours).queryByRole("button", { name: "Guardar horario" })).toBeNull();
  });

  it("«Es correcto» confirms what was read from the web", async () => {
    const user = userEvent.setup();
    page();
    const services = screen.getByRole("region", { name: "Servicios" });
    await user.click(within(services).getByRole("button", { name: "Es correcto" }));
    expect(confirmSection).toHaveBeenCalledWith({ ref: "barberia-cultor", section: "services" });
    expect(within(services).queryByText("Leído de la web · revísalo")).toBeNull();
  });

  it("with the record and the sources, «Documentos y webs» and «Redes sociales» are the last two sections", () => {
    page({
      sources: ok({ items: [], removed: [], max_bytes: 10_000_000, allowed: ["add"] }),
      record: ok({
        spec: { links: [{ id: "l1", network: "instagram", url: null, handle: "cultorbarber" }] },
        valid: true,
        problems: [],
        sections: [{ section: "links", state: "complete", revision: 3, updated_at: null, updated_by: null, origin: null, pending_suggestions: 0 }],
        provenance: {},
        suggestions: [],
        allowed: ["edit"],
      }),
    });
    const index = screen.getByRole("navigation", { name: "Secciones de Negocio" });
    expect(within(index).getAllByRole("link").map((a) => a.textContent?.replace(/(Completa|Pendiente|Opcional|Leída · revísala)$/, ""))).toEqual([
      "Datos básicos",
      "Sedes",
      "Horarios",
      "Servicios",
      "Documentos y webs",
      "Redes sociales",
    ]);
    expect(screen.getByRole("region", { name: "Documentos y webs" })).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Redes sociales" })).getByDisplayValue("cultorbarber")).toBeVisible();
  });

  it("the index scrolls sideways on a phone without widening the page", () => {
    // Recorrido UI de la 047: a 375 px, el estado de cada sección es `sr-only`
    // (absoluto). Si la tira que se desliza no lo contiene, sale por la derecha
    // y la página entera se desliza en horizontal (435 px).
    page();
    const index = screen.getByRole("navigation", { name: "Secciones de Negocio" });
    const strip = index.querySelector("[data-scroll-x]");
    expect(strip?.className).toMatch(/(^|\s)relative(\s|$)/);
  });

  it("empty: each section says what is missing and what the agent will do", () => {
    page();
    expect(screen.getByText("Sin sedes. Si atiende solo online, déjalo vacío.")).toBeVisible();
    expect(screen.getByText(/el agente dirá que no lo sabe/)).toBeVisible();
    expect(screen.getByText(/Todavía no hay servicios/)).toBeVisible();
  });

  it("partial: a section that did not load says so; the rest still work", async () => {
    const user = userEvent.setup();
    page({ services: failed });
    const services = screen.getByRole("region", { name: "Servicios" });
    expect(within(services).getByText("No se pudo cargar esta sección.")).toBeVisible();
    expect(within(services).getByRole("button", { name: "Reintentar" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Horarios" })).toBeVisible();
    await user.click(within(services).getByRole("button", { name: "Reintentar" }));
  });

  it("error: nothing loaded", () => {
    page({ basics: failed, locations: failed, hours: failed, specialDates: failed, services: failed });
    expect(screen.getAllByText("No se pudo cargar esta sección.")).toHaveLength(4);
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
