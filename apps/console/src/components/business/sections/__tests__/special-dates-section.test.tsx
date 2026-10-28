import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { SpecialDates } from "@/lib/backend/business-sections";

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

function section(create = vi.fn()) {
  render(
    <LocaleProvider locale="es">
      <SpecialDatesSection refId="flor-y-encanto" specialDates={EMPTY} locations={[]} canWrite actions={{ create, archive: vi.fn() }} />
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
});
