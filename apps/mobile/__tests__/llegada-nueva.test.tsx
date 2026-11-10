import { fireEvent, render, screen } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { WalkIn } = require("@/features/reservas/walk-in") as typeof import("@/features/reservas/walk-in");
const { NewReservationForm } = require("@/features/reservas/new-reservation") as typeof import("@/features/reservas/new-reservation");

/**
 * Spec 044, Historias 3 y 4, Requisitos 5 y 6: the walk-in at the door, and a
 * new reservation from the phone.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const slots = [780, 810, 840, 870, 900].map((time) => ({ date: TODAY, time, inside: time === 780 ? 50 : 20, capacity: 64, blocked: null, closed: false }));

describe("walk-in (R6.2–R6.4)", () => {
  it("says live that they fit, with what is left until when", async () => {
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 800 }} online busy={false} onRegister={noop} onWait={noop} t={t} />);
    // 2 by default; at 13:00 there are 50 inside the window → 64 − 50 − 2 = 12 left until 14:30.
    expect(screen.getByText("Cabe. Después quedarán 12 libres hasta las 14:30.")).toBeTruthy();
  });

  it("the party is one adjustable control for VoiceOver, with its value in words (gate review)", async () => {
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 800 }} online busy={false} onRegister={noop} onWait={noop} t={t} />);
    const party = screen.getByRole("adjustable");
    expect(party.props.accessibilityValue).toEqual({ text: "2 comensales" });
    await fireEvent(party, "accessibilityAction", { nativeEvent: { actionName: "increment" } });
    expect(screen.getByRole("adjustable").props.accessibilityValue).toEqual({ text: "3 comensales" });
  });

  it("says aloud whether they fit when the party changes — iOS has no live regions (gate review)", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 800 }} online busy={false} onRegister={noop} onWait={noop} t={t} />);
    announce.mockClear();
    await fireEvent.press(screen.getByLabelText("Uno más"));
    expect(announce).toHaveBeenCalledWith("Cabe. Después quedarán 11 libres hasta las 14:30.");
    announce.mockRestore();
  });

  it("registers the arrival with its party and name", async () => {
    const onRegister = jest.fn();
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 800 }} online busy={false} onRegister={onRegister} onWait={noop} t={t} />);
    await fireEvent.press(screen.getByLabelText("Uno más"));
    await fireEvent.changeText(screen.getByLabelText("Nombre (opcional)"), "Ignacio");
    await fireEvent.press(screen.getByText("Registrar llegada"));
    expect(onRegister).toHaveBeenCalledWith(3, "Ignacio");
  });

  it("when they do not fit, offers the waitlist instead", async () => {
    const onWait = jest.fn();
    const full = slots.map((s) => ({ ...s, inside: 63 }));
    await render(<WalkIn config={capacityConfig} slots={full} now={{ date: TODAY, minutes: 800 }} online busy={false} onRegister={noop} onWait={onWait} t={t} />);
    expect(screen.getByText("No cabe ahora. Puedes apuntarlo en la lista de espera.")).toBeTruthy();
    expect(screen.queryByText("Registrar llegada")).toBeNull();
    await fireEvent.press(screen.getByText("Apuntar en lista de espera"));
    expect(onWait).toHaveBeenCalledWith(2, null);
  });

  it("says a failed arrival inside the sheet, not in a notice under it (gate review)", async () => {
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 800 }} online busy={false} error="Ya no cabe: se llenó mientras tanto." onRegister={noop} onWait={noop} t={t} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Ya no cabe: se llenó mientras tanto.")).toBeTruthy();
  });

  it("outside the shifts there is no service", async () => {
    await render(<WalkIn config={capacityConfig} slots={slots} now={{ date: TODAY, minutes: 17 * 60 }} online busy={false} onRegister={noop} onWait={noop} t={t} />);
    expect(screen.getByText("Ahora no hay servicio.")).toBeTruthy();
    expect(screen.queryByText("Registrar llegada")).toBeNull();
  });
});

describe("new reservation · Servicios (R5.2, R5.5–R5.8)", () => {
  const free = [
    { time: 17 * 60, pro: { id: "p-marcos", name: "Marcos Soto" }, left: null, full: false },
    { time: 17 * 60 + 30, pro: { id: "p-javiera", name: "Javiera Muñoz" }, left: null, full: false },
  ];

  it("asks for the service, with whom and the day, and shows the real slots with who would do them", async () => {
    const onQuery = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={onQuery} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(onQuery).toHaveBeenLastCalledWith({ date: TODAY, serviceId: "s-corte", proId: null });
    await fireEvent.press(screen.getByText("Mañana"));
    expect(onQuery).toHaveBeenLastCalledWith({ date: "2026-10-23", serviceId: "s-corte", proId: null });
    expect(screen.getByLabelText("17:00 con Marcos Soto")).toBeTruthy();
  });

  it("if the slots cannot be read, it says so with «Reintentar», never «no quedan huecos» (gate review)", async () => {
    const onRetrySlots = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={null} slotsLoading={false} slotsError onRetrySlots={onRetrySlots} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.queryByText(/No quedan huecos/)).toBeNull();
    expect(screen.getByText("No se pudieron cargar las horas libres.")).toBeTruthy();
    await fireEvent.press(screen.getByText("Reintentar"));
    expect(onRetrySlots).toHaveBeenCalled();
  });

  it("a last row with fewer times keeps the same width per time (first iOS pass)", async () => {
    const five = Array.from({ length: 5 }, (_, i) => ({ time: 12 * 60 + i * 30, pro: { id: "p-marcos", name: "Marcos Soto" }, left: null, full: false }));
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={five} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    // Four to a row: the fifth is followed by three empty places, so it does not stretch.
    expect(screen.getAllByTestId("slot-filler", { includeHiddenElements: true })).toHaveLength(3);
  });

  it("saves once with a name and a time, and says the summary", async () => {
    const onSave = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={noop} onSave={onSave} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.getByRole("button", { name: "Guardar reserva" }).props.accessibilityState).toMatchObject({ disabled: true });
    await fireEvent.press(screen.getByLabelText("17:00 con Marcos Soto"));
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Lucía Fernández");
    expect(screen.getByText("Hoy a las 17:00 · Corte con Marcos")).toBeTruthy();
    await fireEvent.press(screen.getByText("Guardar reserva"));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({
      date: TODAY,
      time: 17 * 60,
      customer: { name: "Lucía Fernández", phone: null },
      serviceId: "s-corte",
      proId: "p-marcos",
    });
  });

  it("says when there are no slots", async () => {
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={[]} slotsLoading={false} onQuery={noop} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(screen.getByText("No quedan huecos ese día. Prueba otro día o con otra persona.")).toBeTruthy();
  });
});

describe("new reservation · Aforo (R5.3, R5.4)", () => {
  const free = [
    { time: 13 * 60, pro: null, left: 2, full: true },
    { time: 13 * 60 + 30, pro: null, left: 14, full: false },
  ];

  it("asks for the party; a full time cannot be chosen; above the maximum it warns but lets you", async () => {
    const onQuery = jest.fn();
    await render(
      <NewReservationForm config={capacityConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={onQuery} onSave={noop} saving={false} error={null} online t={t} locale="es" />,
    );
    expect(onQuery).toHaveBeenLastCalledWith({ date: TODAY, partySize: 2 });
    expect(screen.getByLabelText("13:00, completo").props.accessibilityState).toMatchObject({ disabled: true });
    expect(screen.getByLabelText("13:30, quedan 14")).toBeTruthy();
    for (let i = 0; i < 9; i++) await fireEvent.press(screen.getByLabelText("Uno más"));
    expect(screen.getByText("Más de 10: el agente no acepta grupos así, pero tú sí puedes reservarlos.")).toBeTruthy();
  });
});
