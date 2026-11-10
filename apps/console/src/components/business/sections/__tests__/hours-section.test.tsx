import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Hours, Location } from "@/lib/backend/business-sections";

vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  saveHoursAction: vi.fn(),
  loadHoursAction: vi.fn(),
}));

const { HoursSection } = await import("../hours-section");

/**
 * Spec 047 (T060, historia 5) — el horario en Negocio: por bloques o día por
 * día, turnos, «Nocturno · cierra al día siguiente», la frase «Así lo dirá el
 * agente», el aviso de lo que se pierde al pasar a bloques (10.6), el horario
 * propio de una sede y el modo de solo lectura.
 */

const s = (open: string, close: string, overnight = false) => ({ open, close, overnight });
const DAILY: Hours = {
  revision: 4,
  state: "complete",
  allowed: ["edit"],
  location_id: null,
  inherits: false,
  layout: "daily",
  days: {
    mon: [s("09:00", "14:00"), s("16:00", "20:00")],
    tue: [s("10:00", "14:00")],
    wed: [s("09:00", "14:00"), s("16:00", "20:00")],
    thu: [s("09:00", "14:00"), s("16:00", "20:00")],
    fri: [s("20:00", "02:00", true)],
    sat: [],
    sun: [],
  },
  label: "Abrimos lunes de 09:00 a 14:00 y de 16:00 a 20:00…",
};
const CENTRO: Location = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Cultor Centro",
  address: "Calle Mayor 1",
  phone_e164: null,
  own_hours: false,
  label: null,
  archived: false,
};

type Saved = { ok: true; data: Hours } | { ok: false; status: number; message: string; code?: string | null; info?: Record<string, unknown> };

function section(props: Partial<React.ComponentProps<typeof HoursSection>> = {}) {
  const save = vi.fn<(b: unknown) => Promise<Saved>>(async () => ({ ok: true, data: DAILY }));
  const load = vi.fn<(b: unknown) => Promise<Saved>>(async () => ({ ok: true, data: { ...DAILY, location_id: CENTRO.id, inherits: true } }));
  const view = render(
    <LocaleProvider locale="es">
      <HoursSection refId="barberia-cultor" hours={DAILY} locations={[CENTRO]} canWrite save={save} load={load} {...props} />
    </LocaleProvider>,
  );
  return { ...view, save, load };
}

/** Como el prototipo: se lee primero; el editor se abre con «Editar». */
async function editing(props: Partial<React.ComponentProps<typeof HoursSection>> = {}) {
  const user = userEvent.setup();
  const view = section(props);
  await user.click(screen.getByRole("button", { name: "Editar Horarios" }));
  return { ...view, user };
}

describe("HoursSection", () => {
  it("reads first: the days grouped and the phrase the agent will say", async () => {
    const { container } = section();
    expect(screen.getByText(`Así lo dirá el agente: «${DAILY.label as string}»`)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar horario" })).toBeNull();
    expect(screen.getAllByText("Cerrado").length).toBeGreaterThan(0);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Cancelar» closes the editor without saving", async () => {
    const { user, save } = await editing();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Editar Horarios" })).toBeVisible();
  });

  it("the editor shows the night shift label", async () => {
    const { container } = await editing();
    const friday = screen.getByRole("group", { name: "Viernes" });
    expect(within(friday).getByText("Nocturno · cierra al día siguiente")).toBeVisible();
    expect(within(screen.getByRole("group", { name: "Sábado" })).getByText("Cerrado")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("asks before switching to blocks and says which days would be lost", async () => {
    const { user } = await editing();
    await user.click(screen.getByRole("radio", { name: "Por bloques" }));
    const dialog = await screen.findByRole("dialog", { name: "Pasar a «Por bloques»" });
    expect(within(dialog).getByText(/martes, viernes/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("radio", { name: "Día por día" })).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "Por bloques" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Pasar a bloques" }));
    expect(screen.getByRole("radio", { name: "Por bloques" })).toBeChecked();
    expect(screen.getByRole("group", { name: "Lunes a viernes" })).toBeVisible();
  });

  it("allows up to six shifts a day", async () => {
    const { user } = await editing();
    const tuesday = screen.getByRole("group", { name: "Martes" });
    const add = within(tuesday).getByRole("button", { name: "Añadir turno" });
    for (let i = 0; i < 5; i++) await user.click(add);
    expect(within(tuesday).getAllByLabelText(/^Abre/)).toHaveLength(6);
    expect(add).toBeDisabled();
    expect(within(tuesday).getByText("Como mucho 6 turnos por día.")).toBeVisible();
  });

  it("saves with the revision it read and tells a conflict apart", async () => {
    const { user, save } = await editing();
    await user.click(screen.getByRole("button", { name: "Guardar horario" }));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ ref: "barberia-cultor", revision: 4, locationId: null }));
    // Guardado, vuelve a la lectura.
    await waitFor(() => expect(screen.getByRole("button", { name: "Editar Horarios" })).toBeVisible());
    save.mockResolvedValueOnce({ ok: false, status: 412, message: "conflict", code: "revision_conflict" });
    await user.click(screen.getByRole("button", { name: "Editar Horarios" }));
    await user.click(screen.getByRole("button", { name: "Guardar horario" }));
    expect(await screen.findByText(/Alguien cambió esta sección/)).toBeVisible();
  });

  it("edits a location's own hours or uses the business's", async () => {
    const { user, load } = await editing();
    await user.selectOptions(screen.getByRole("combobox", { name: "Horario de" }), CENTRO.id);
    expect(load).toHaveBeenCalledWith(expect.objectContaining({ locationId: CENTRO.id }));
    expect(await screen.findByRole("checkbox", { name: "Usar el horario del negocio" })).toBeChecked();
  });

  it("is read-only without permission", () => {
    section({ canWrite: false });
    expect(screen.queryByRole("button", { name: "Guardar horario" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Añadir turno" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Editar Horarios" })).toBeNull();
    expect(screen.getAllByText(/09:00 – 14:00/).length).toBeGreaterThan(0);
  });

  it("without hours says what the agent will do", () => {
    section({ hours: { ...DAILY, layout: null, label: null, state: "pending", days: { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] } } });
    expect(screen.getByText(/el agente dirá que no lo sabe/)).toBeVisible();
  });
});
