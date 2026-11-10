import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { SpecialDates } from "@/lib/backend/business-sections";

import type { SpecialDatesActions } from "../special-dates-section";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  createSpecialDateAction: vi.fn(),
  archiveSpecialDateAction: vi.fn(),
}));

const { SpecialDatesSection } = await import("../special-dates-section");

/**
 * Spec 047 (T060, requisito 10.3): «Fechas especiales» en el Negocio del partner
 * (y de la lite, que usa la misma sección). El recorrido UI encontró que, sin
 * «Desde», el formulario decía «La fecha final no puede ser anterior a la
 * inicial»: falta la fecha, no está al revés.
 */
const EMPTY: SpecialDates = { allowed: ["edit"], revision: 2, state: "optional", items: [], created_id: null };

function section(create = vi.fn(), o: { dates?: SpecialDates; archive?: SpecialDatesActions["archive"] } = {}) {
  render(
    <LocaleProvider locale="es">
      <SpecialDatesSection
        refId="flor-y-encanto"
        specialDates={o.dates ?? EMPTY}
        locations={[]}
        canWrite
        today="2026-11-07"
        actions={{ create, archive: o.archive ?? vi.fn() }}
      />
    </LocaleProvider>,
  );
  return create;
}

describe("SpecialDatesSection", () => {
  it("sin «Desde» pide la fecha, y no dice que esté al revés", async () => {
    const user = userEvent.setup();
    const create = section();
    await user.click(screen.getByRole("button", { name: "Añadir fecha especial" }));
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(screen.getByRole("alert").textContent).toBe("Elige el día en que empieza.");
    expect(create).not.toHaveBeenCalled();
  });

  it("con el final antes del inicio, lo dice", async () => {
    const user = userEvent.setup();
    const create = section();
    await user.click(screen.getByRole("button", { name: "Añadir fecha especial" }));
    fireEvent.change(screen.getByLabelText(/Desde/), { target: { value: "2026-12-26" } });
    fireEvent.change(screen.getByLabelText(/Hasta/), { target: { value: "2026-12-24" } });
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(screen.getByRole("alert").textContent).toBe("La fecha final no puede ser anterior a la inicial.");
    expect(create).not.toHaveBeenCalled();
  });

  it("un día cerrado se guarda con la revisión leída", async () => {
    const user = userEvent.setup();
    const create = section(vi.fn(async () => ({ ok: true as const, data: EMPTY })));
    await user.click(screen.getByRole("button", { name: "Añadir fecha especial" }));
    await user.type(screen.getByLabelText(/Nombre/), "Navidad");
    fireEvent.change(screen.getByLabelText(/Desde/), { target: { value: "2026-12-25" } });
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        ref: "flor-y-encanto",
        revision: 2,
        body: { name: "Navidad", location_id: null, from: "2026-12-25", to: "2026-12-25", closed: true, shifts: [] },
      }),
    );
  });

  it("spec 056 (11.4, D10): a date whose «Hasta» already passed is refused before asking", async () => {
    const user = userEvent.setup();
    const create = section(vi.fn(async () => ({ ok: true as const, data: EMPTY })));
    await user.click(screen.getByRole("button", { name: "Añadir fecha especial" }));
    fireEvent.change(screen.getByLabelText(/Desde/), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText(/Hasta/), { target: { value: "2026-11-06" } });
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(screen.getByRole("alert").textContent).toBe("Esa fecha ya pasó: el «Hasta» es anterior a hoy.");
    expect(create).not.toHaveBeenCalled();
    // A closing that started and has not ended yet is fine.
    fireEvent.change(screen.getByLabelText(/Hasta/), { target: { value: "2026-11-08" } });
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    await waitFor(() => expect(create).toHaveBeenCalled());
  });

  it("spec 056 (11.4): the API's «date_past» is said in words", async () => {
    const user = userEvent.setup();
    section(vi.fn(async () => ({ ok: false as const, status: 422, message: "x", code: "date_past" })));
    await user.click(screen.getByRole("button", { name: "Añadir fecha especial" }));
    fireEvent.change(screen.getByLabelText(/Desde/), { target: { value: "2026-11-07" } });
    await user.click(screen.getByRole("button", { name: "Guardar fecha" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Esa fecha ya pasó: el «Hasta» es anterior a hoy.");
  });

  it("spec 056 (12.1): removing a date asks first", async () => {
    const user = userEvent.setup();
    const archive = vi.fn(async () => ({ ok: true as const, data: EMPTY }));
    const navidad = { id: "11111111-1111-4111-8111-111111111111", name: "Navidad", location_id: null, from: "2026-12-25", to: "2026-12-25", closed: true, shifts: [], archived: false };
    section(vi.fn(), { dates: { ...EMPTY, items: [navidad] }, archive });
    await user.click(screen.getByRole("button", { name: "Quitar Navidad" }));
    const ask = await screen.findByRole("dialog", { name: "¿Quitar «Navidad»?" });
    expect(archive).not.toHaveBeenCalled();
    await user.click(within(ask).getByRole("button", { name: "Quitar" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith({ ref: "flor-y-encanto", revision: 2, id: navidad.id }));
  });
});
