import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Hours, Locations, Services, SpecialDates } from "@/lib/backend/business-sections";
import type { LiteBusiness } from "@/lib/backend/lite-agents";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/negocio/actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({}));

const { LiteBusinessView } = await import("../lite-business");
type Actions = NonNullable<React.ComponentProps<typeof LiteBusinessView>["actions"]>;

/**
 * Spec 047 (T168; requisitos 50.1, 50.3 y 50.4) — «Negocio» de la consola lite:
 * las cuatro secciones de la ficha que edita el negocio, sin lo que es del
 * partner (duplicar, quién lo ofrece, renombrar un servicio), con `If-Match` e
 * `Idempotency-Key` en cada escritura, y «Últimos cambios» con «Deshacer».
 */

const SVC = "00000000-0000-4000-8000-0000000000b1";
const CHANGE = "00000000-0000-4000-8000-0000000000e9";
const empty = { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };

function business(over: Partial<LiteBusiness> = {}): LiteBusiness {
  const hours: Hours = {
    revision: 4,
    state: "complete",
    allowed: ["edit"],
    location_id: null,
    inherits: false,
    layout: "daily",
    days: { ...empty, mon: [{ open: "10:00", close: "20:00", overnight: false }], sat: [{ open: "10:00", close: "14:00", overnight: false }] },
    label: "De lunes a sábado, de 10:00 a 20:00",
  };
  const special: SpecialDates = { revision: 1, state: "optional", allowed: ["edit"], items: [], created_id: null };
  const services: Services = {
    revision: 7,
    state: "complete",
    allowed: ["edit"],
    currency: "EUR",
    exponent: 2,
    agents: [],
    created_id: null,
    items: [
      {
        id: SVC,
        name: "Corte clásico",
        description: null,
        bookable: true,
        duration_min: 30,
        price: { kind: "amount", amount_minor: 1500 },
        currency: "EUR",
        staff: "all",
        agents: { mode: "all_agents", agent_ids: [] },
        used_by: [{ id: "a1", name: "Recepción" }],
        archived: false,
      },
    ],
  };
  const locations: Locations = { revision: 2, state: "optional", allowed: ["edit"], items: [], created_id: null };
  return {
    hours,
    special_dates: special,
    services,
    locations,
    provenance: {},
    history: [{ id: CHANGE, section: "services", kind: "update", at: "2026-10-27T10:00:00Z", by: { kind: "client_user", name: "Marta" }, origin: "lite_web", undone_at: null, undoable: true }],
    ...over,
  };
}

const ok = <T,>(data: T) => ({ ok: true as const, data });

function view(data: LiteBusiness | null, over: Partial<Actions> = {}) {
  const fresh = business();
  const actions: Actions = {
    reload: vi.fn(async () => ok(fresh)),
    loadHours: vi.fn(async () => ok(fresh.hours)),
    saveHours: vi.fn(async () => ok(fresh.hours)),
    createSpecialDate: vi.fn(async () => ok(fresh.special_dates)),
    archiveSpecialDate: vi.fn(async () => ok(fresh.special_dates)),
    createService: vi.fn(async () => ok(fresh.services)),
    updateService: vi.fn(async () => ok(fresh.services)),
    archiveService: vi.fn(async () => ok(fresh.services)),
    createLocation: vi.fn(async () => ok(fresh.locations)),
    updateLocation: vi.fn(async () => ok(fresh.locations)),
    archiveLocation: vi.fn(async () => ok(fresh.locations)),
    undo: vi.fn(async () => ok({ section: "services", revision: 8, change_id: "00000000-0000-4000-8000-0000000000ea" })),
    ...over,
  };
  const r = render(
    <LocaleProvider locale="es">
      <LiteBusinessView initial={data} actions={actions} />
    </LocaleProvider>,
  );
  return { ...r, actions };
}

// Estas pantallas son grandes y axe tarda: con la máquina cargada, 5 s no bastan.
describe("«Negocio» de la consola lite (T168)", { timeout: 60_000 }, () => {
  it("pinta el horario, las fechas especiales, los servicios, las sedes y los últimos cambios, y pasa axe", async () => {
    const { container } = view(business());
    for (const name of ["Horario", "Fechas especiales", "Servicios", "Sedes", "Últimos cambios"]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("De lunes a sábado, de 10:00 a 20:00")).toBeInTheDocument();
    // Lo que es del partner no se ofrece (50.3).
    expect(screen.queryByRole("button", { name: /Duplicar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Quién lo ofrece|Quién ofrece/ })).toBeNull();
    expect(screen.queryByText("Datos básicos")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("cambiar el precio de un servicio no manda el nombre, y lleva `Idempotency-Key`", async () => {
    const user = userEvent.setup();
    const { actions } = view(business());
    await user.click(screen.getByRole("button", { name: "Editar Corte clásico" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByRole("textbox", { name: /Nombre/ });
    expect(name).toHaveAttribute("readonly");
    expect(within(dialog).getByText("El nombre lo cambia quien gestiona tus agentes.")).toBeInTheDocument();
    const amount = within(dialog).getByRole("textbox", { name: /Importe/ });
    await user.clear(amount);
    await user.type(amount, "18");
    await user.click(within(dialog).getByRole("button", { name: /Guardar/ }));
    await waitFor(() => expect(actions.updateService).toHaveBeenCalled());
    const call = vi.mocked(actions.updateService).mock.calls[0]![0];
    expect(call.revision).toBe(7);
    expect(call.id).toBe(SVC);
    expect(call.body).not.toHaveProperty("name");
    expect(call.body.price).toEqual({ kind: "amount", amount_minor: 1800 });
    expect(call.key).toMatch(/.{8,}/);
    // Después de escribir, el historial se vuelve a leer.
    await waitFor(() => expect(actions.reload).toHaveBeenCalled());
  });

  it("guardar el horario manda la revisión que leyó la pantalla", async () => {
    const user = userEvent.setup();
    const { actions } = view(business());
    await user.click(within(screen.getByRole("region", { name: "Horario" })).getByRole("button", { name: /Guardar/ }));
    await waitFor(() => expect(actions.saveHours).toHaveBeenCalled());
    expect(vi.mocked(actions.saveHours).mock.calls[0]![0]).toMatchObject({ revision: 4, location_id: null, body: { layout: "daily" } });
  });

  it("una sede lee su propio horario y lo guarda con su id", async () => {
    const user = userEvent.setup();
    const CENTRO = "00000000-0000-4000-8000-0000000000c1";
    const data = business({
      locations: {
        revision: 2,
        state: "optional",
        allowed: ["edit"],
        created_id: null,
        items: [{ id: CENTRO, name: "Centro", address: "Calle Mayor 1", phone_e164: null, own_hours: true, label: null, archived: false }],
      },
    });
    const own: Hours = { ...data.hours, revision: 9, location_id: CENTRO, inherits: false, label: "Sábados de 10:00 a 14:00" };
    const { actions } = view(data, { loadHours: vi.fn(async () => ok(own)), saveHours: vi.fn(async () => ok(own)) });
    const hours = screen.getByRole("region", { name: "Horario" });
    await user.selectOptions(within(hours).getByLabelText("Horario de"), "Centro");
    await waitFor(() => expect(actions.loadHours).toHaveBeenCalledWith({ location_id: CENTRO }));
    await user.click(within(hours).getByRole("button", { name: /Guardar/ }));
    await waitFor(() => expect(actions.saveHours).toHaveBeenCalled());
    expect(vi.mocked(actions.saveHours).mock.calls[0]![0]).toMatchObject({ revision: 9, location_id: CENTRO });
  });

  it("«Deshacer» el último cambio vuelve a leer la ficha; un 412 lo dice sin pisar a nadie", async () => {
    const user = userEvent.setup();
    const { actions } = view(business());
    const history = screen.getByRole("region", { name: "Últimos cambios" });
    expect(within(history).getByText(/Marta · desde la web/)).toBeInTheDocument();
    await user.click(within(history).getByRole("button", { name: "Deshacer el cambio de Servicios" }));
    await waitFor(() => expect(actions.undo).toHaveBeenCalledWith(expect.objectContaining({ id: CHANGE })));
    await waitFor(() => expect(actions.reload).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("Cambio deshecho. El agente vuelve a usar lo de antes.");

    const conflict = vi.fn(async () => ({ ok: false as const, status: 412, message: "x", code: "revision_conflict" }));
    vi.mocked(toast.error).mockClear();
    const second = view(business(), { undo: conflict });
    await user.click(within(second.container).getAllByRole("button", { name: "Deshacer el cambio de Servicios" })[0]!);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Alguien cambió esa parte después. No se ha deshecho para no pisar su cambio."));
  });

  it("si la ficha no llega, lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const { actions } = view(null);
    expect(screen.getByText("No pudimos leer tu negocio")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(actions.reload).toHaveBeenCalled());
    expect(await screen.findByRole("region", { name: "Horario" })).toBeInTheDocument();
  });
});
