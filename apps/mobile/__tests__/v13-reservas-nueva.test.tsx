import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { NewReservationForm } = require("@/features/reservas/new-reservation") as typeof import("@/features/reservas/new-reservation");
const { MoveForm } = require("@/features/reservas/move-reservation") as typeof import("@/features/reservas/move-reservation");

/**
 * Spec 069, Requisitos 15 y 14.3: «Nueva reserva» as the design has it — the
 * seven open days, the times in morning and afternoon with the taken ones in
 * place, none before the agent's notice, the time brought from the grid, and
 * closing that asks — and «Mover la reserva», only to free slots.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const now = { date: TODAY, minutes: 11 * 60 + 20 };
const at = (m: number, pro = { id: "p-marcos", name: "Marcos Soto" }) => ({ time: m, pro, left: null, full: false });

describe("the day and the time (R15.1, R15.2)", () => {
  it("offers the seven open days ahead, Sunday left out", async () => {
    await render(<NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={[]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />);
    const days = screen.getAllByTestId(/^day-/).map((n) => String(n.props.testID).slice(4));
    expect(days).toEqual(["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]);
  });

  it("groups the times in morning and afternoon, the taken ones struck through and not choosable", async () => {
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate="2026-10-23" slots={[at(9 * 60), at(16 * 60)]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.getByText("Mañana · 1 hueco libre")).toBeTruthy();
    expect(screen.getByText("Tarde · 1 hueco libre")).toBeTruthy();
    const taken = screen.getByLabelText("09:30, ocupada");
    expect(taken.props.accessibilityState).toMatchObject({ disabled: true });
    expect(StyleSheet.flatten(within(taken).getByText("09:30").props.style).textDecorationLine).toBe("line-through");
  });

  it("offers no time before now plus the agent's notice, and says why", async () => {
    await render(
      <NewReservationForm
        config={{ ...servicesConfig, agent: { minNoticeMin: 60 } }}
        today={TODAY}
        initialDate={TODAY}
        now={now}
        slots={[at(11 * 60 + 30), at(12 * 60 + 30)]}
        slotsLoading={false}
        onQuery={noop}
        onSave={noop}
        saving={false}
        error={null}
        online
        t={t}
        locale="es"
      />,
    );
    expect(screen.queryByTestId("slot-11:30")).toBeNull();
    expect(screen.queryByTestId("slot-12:00")).toBeNull();
    expect(screen.getByLabelText("12:30 con Marcos Soto")).toBeTruthy();
    expect(screen.getByText("Las horas antes de las 12:20 no salen: es la antelación mínima del agente.")).toBeTruthy();
  });

  it("a notice of 24 h covers today whole, and says from when it offers", async () => {
    await render(
      <NewReservationForm config={{ ...servicesConfig, agent: { minNoticeMin: 1440 } }} today={TODAY} initialDate={TODAY} now={now} slots={[at(16 * 60)]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.queryByTestId("slot-16:00")).toBeNull();
    expect(screen.getByText("Este día queda dentro de la antelación mínima del agente: la primera hora que se ofrece es mañana a las 11:20.")).toBeTruthy();
  });

  it("the chosen time draws its check (micro 2)", async () => {
    await render(<NewReservationForm config={servicesConfig} today={TODAY} initialDate="2026-10-23" slots={[at(16 * 60)]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />);
    await fireEvent.press(screen.getByLabelText("16:00 con Marcos Soto"));
    const chosen = screen.getByLabelText("16:00 con Marcos Soto");
    expect(chosen.props.accessibilityState).toMatchObject({ checked: true });
    expect(within(chosen).getByTestId("slot-check")).toBeTruthy();
  });
});

describe("what the way in brings (R13.3, R16.3)", () => {
  it("a free slot of the grid comes chosen", async () => {
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate="2026-10-23" initial={{ time: 16 * 60, proId: "p-marcos" }} slots={[at(16 * 60)]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.getByText("Mañana a las 16:00 · Corte con Marcos")).toBeTruthy();
  });

  it("and if the API no longer offers it, it says so instead of dropping it silently", async () => {
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate="2026-10-23" initial={{ time: 16 * 60 }} slots={[at(17 * 60)]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.getByText("Las 16:00 ya no están libres. Elige otra hora.")).toBeTruthy();
  });

  it("someone of the waitlist comes with their name, phone and service", async () => {
    const onSave = jest.fn();
    await render(
      <NewReservationForm
        config={servicesConfig}
        today={TODAY}
        initialDate="2026-10-23"
        initial={{ name: "Florencia Araya", phone: "+56 9 7788 1122", serviceId: "s-peinado" }}
        slots={[at(16 * 60)]}
        slotsLoading={false}
        onQuery={noop}
        onSave={onSave}
        saving={false}
        error={null}
        online
        t={t}
        locale="es"
      />,
    );
    await fireEvent.press(screen.getByLabelText("16:00 con Marcos Soto"));
    await fireEvent.press(screen.getByRole("button", { name: "Guardar reserva" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ serviceId: "s-peinado", customer: { name: "Florencia Araya", phone: "+56 9 7788 1122" } }));
  });
});

describe("closing with something written asks first (R15.3)", () => {
  it("says when something was written, and offers «Cerrar»", async () => {
    const onDirty = jest.fn();
    const onClose = jest.fn();
    await render(<NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={[]} slotsLoading={false} onQuery={noop} onSave={noop} onDirty={onDirty} onClose={onClose} saving={false} error={null} online t={t} locale="es" />);
    expect(onDirty).toHaveBeenLastCalledWith(false);
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Ana");
    expect(onDirty).toHaveBeenLastCalledWith(true);
    await fireEvent.press(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("a form that opens filled is not «written» yet", () => {
  it("«Reservarle ahora» brings a name and a phone, and closing does not ask until something changes", async () => {
    const onDirty = jest.fn();
    await render(
      <NewReservationForm
        config={servicesConfig}
        today={TODAY}
        initialDate={TODAY}
        initial={{ name: "Florencia Araya", phone: "+56 9 7788 1122" }}
        slots={[]}
        slotsLoading={false}
        onQuery={noop}
        onSave={noop}
        onDirty={onDirty}
        saving={false}
        error={null}
        online
        t={t}
        locale="es"
      />,
    );
    expect(onDirty).toHaveBeenLastCalledWith(false);
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "+56 9 7788 1123");
    expect(onDirty).toHaveBeenLastCalledWith(true);
  });
});

describe("moving a reservation (R14.3)", () => {
  const r = res({
    id: "m",
    date: "2026-10-23",
    start: 17 * 60,
    end: 17 * 60 + 45,
    service: peinado,
    pro: marcos,
    customer: { name: "Lucía Fernández", phone: "+56 9 6123 4567" },
    moreActions: ["move"],
  });

  it("asks the API without counting itself, and never offers the time it already has", async () => {
    const onQuery = jest.fn();
    await render(
      <MoveForm r={r} config={servicesConfig} today={TODAY} now={now} slots={[at(16 * 60), at(17 * 60)]} slotsLoading={false} onQuery={onQuery} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(onQuery).toHaveBeenLastCalledWith({ date: "2026-10-23", serviceId: "s-peinado", proId: "p-marcos", exclude: "m" });
    expect(screen.getByText("Lucía Fernández · ahora es Mañana · 17:00 – 17:45")).toBeTruthy();
    expect(screen.queryByTestId("slot-17:00")).toBeNull();
    expect(screen.getByLabelText("16:00 con Marcos Soto")).toBeTruthy();
  });

  it("moves to the chosen free time, telling the customer unless the person says not to", async () => {
    const onSave = jest.fn();
    await render(
      <MoveForm r={r} config={servicesConfig} today={TODAY} now={now} slots={[at(16 * 60)]} slotsLoading={false} onQuery={noop} onSave={onSave} saving={false} error={null} online t={t} locale="es" />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Mover reserva" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Elige una hora.")).toBeTruthy();
    await fireEvent.press(screen.getByLabelText("16:00 con Marcos Soto"));
    await fireEvent(screen.getByRole("switch", { name: "Avisar a Lucía del cambio por WhatsApp" }), "valueChange", false);
    await fireEvent.press(screen.getByRole("button", { name: "Mover reserva" }));
    expect(onSave).toHaveBeenCalledWith({ date: "2026-10-23", time: 960, notify: false, proId: "p-marcos" });
  });
});
