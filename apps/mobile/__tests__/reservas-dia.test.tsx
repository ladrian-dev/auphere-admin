import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, corte, javiera, marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { DayHeader } = require("@/features/reservas/header") as typeof import("@/features/reservas/header");
const { DayServices } = require("@/features/reservas/day-services") as typeof import("@/features/reservas/day-services");
const { DayGrid } = require("@/features/reservas/day-grid") as typeof import("@/features/reservas/day-grid");
const { DayCapacity } = require("@/features/reservas/day-capacity") as typeof import("@/features/reservas/day-capacity");
const { ReservasBody } = require("@/features/reservas/body") as typeof import("@/features/reservas/body");

/**
 * RNTL 14: `render` and `fireEvent` are async — an un-awaited press leaves the
 * next test's tree empty.
 *
 * Spec 044, Historia 1, Requisitos 1.3, 2.1–2.11, 16.1, 18.1: a day of
 * Reservas in each mode, and the states of the screen.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;

describe("the day header (R2.2, R2.3, R2.4)", () => {
  it("marks today and the closed days in the strip, and offers «Hoy» only away from today", async () => {
    const onDate = jest.fn();
    await render(
      <DayHeader period="day" onPeriod={noop} date="2026-10-24" today={TODAY} onDate={onDate} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />,
    );
    expect(screen.getByLabelText("Jueves, 22 de octubre, hoy")).toBeTruthy();
    expect(screen.getByLabelText("Domingo, 25 de octubre, cerrado")).toBeTruthy();
    await fireEvent.press(screen.getByText("Hoy"));
    expect(onDate).toHaveBeenCalledWith(TODAY);
  });

  it("a closed day reads at 4.5:1 and says it by more than colour: its number is struck through (gate review)", async () => {
    const lightPalette = (require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen")).tokens.light;
    await render(
      <DayHeader period="day" onPeriod={noop} date="2026-10-24" today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />,
    );
    const closed = within(screen.getByLabelText("Domingo, 25 de octubre, cerrado")).getByText("25");
    const style = StyleSheet.flatten(closed.props.style);
    expect(style.color).not.toBe(lightPalette.subtle);
    expect(style.textDecorationLine).toBe("line-through");
  });

  it("offers List or Grid in Servicios' day", async () => {
    await render(<DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />);
    expect(screen.getByLabelText("Vista")).toBeTruthy();
    expect(screen.queryByText("Hoy")).toBeNull();
  });

  it("and not in Aforo", async () => {
    await render(<DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={capacityConfig} view="list" onView={noop} t={t} locale="es" />);
    expect(screen.queryByLabelText("Vista")).toBeNull();
  });
});

describe("Servicios · day (R2.4, R2.5, R2.6, R2.10)", () => {
  const items = [
    res({ id: "a", start: 600, end: 630, service: corte, pro: marcos, state: "done" }),
    res({ id: "b", start: 690, end: 735, service: peinado, pro: javiera, state: "pending", customer: { name: "Camila Rojas", phone: null } }),
    res({ id: "c", start: 720, end: 750, service: corte, pro: marcos, state: "confirmed", customer: { name: "Tomás Silva", phone: null } }),
    res({ id: "d", start: 780, end: 810, service: corte, pro: marcos, state: "cancelled" }),
  ];
  const now = { date: TODAY, minutes: 11 * 60 + 20 };

  it("sums the day without the cancelled ones and draws «Ahora» between rows", async () => {
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(screen.getByText("3 reservas · 1 sin confirmar")).toBeTruthy();
    expect(screen.getByText("Ahora · 11:20")).toBeTruthy();
    expect(screen.getByLabelText(/11:30, Camila Rojas, Corte y peinado · Javiera Muñoz, Sin confirmar/)).toBeTruthy();
  });

  it("says a past one is past (dimmed, not by opacity)", async () => {
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(screen.getByTestId("res-a").props.accessibilityLabel).toMatch(/ya pasó/);
    expect(screen.getByTestId("res-c").props.accessibilityLabel).not.toMatch(/ya pasó/);
  });

  it("filters by team member", async () => {
    const onPro = jest.fn();
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={onPro} onOpen={noop} t={t} locale="es" />);
    await fireEvent.press(screen.getByText("Marcos"));
    expect(onPro).toHaveBeenCalledWith("p-marcos");
  });

  it("shows only that member's bookings, and opens one", async () => {
    const onOpen = jest.fn();
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro="p-marcos" onPro={noop} onOpen={onOpen} t={t} locale="es" />);
    expect(screen.queryByTestId("res-b")).toBeNull();
    await fireEvent.press(screen.getByTestId("res-c"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "c" }));
  });

  it("filtered to someone with nothing that day, says so and offers the whole team (gate review)", async () => {
    const onPro = jest.fn();
    await render(<DayServices config={servicesConfig} items={[items[1]!]} now={now} date={TODAY} pro="p-marcos" onPro={onPro} onOpen={noop} t={t} locale="es" />);
    expect(screen.queryByText("No hay reservas este día.")).toBeNull();
    expect(screen.getByText("Marcos Soto no tiene reservas este día.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Ver todo el equipo" }));
    expect(onPro).toHaveBeenCalledWith(null);
  });

  it("says when the day is closed", async () => {
    await render(<DayServices config={servicesConfig} items={[]} now={now} date="2026-10-25" pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(screen.getByText("Cerrado este día. Viene del horario del negocio.")).toBeTruthy();
  });

  it("says when the day is empty", async () => {
    await render(<DayServices config={servicesConfig} items={[]} now={now} date="2026-10-23" pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(screen.getByText("No hay reservas este día.")).toBeTruthy();
  });

  it("with large text, the time column grows instead of breaking «11:3 / 0» (gate review)", async () => {
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    const time = screen.getByText("11:30");
    expect(time.props.numberOfLines).toBe(1);
  });

  it("a long service keeps its duration short enough for the time column (first iOS pass)", async () => {
    const color = { id: "s-color", name: "Color", durationMin: 90, price: 35000 };
    await render(
      <DayServices config={servicesConfig} items={[res({ id: "e", start: 750, end: 840, service: color, pro: javiera })]} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />,
    );
    expect(screen.getByText("1 h 30")).toBeTruthy();
    expect(screen.queryByText("1 h 30 min")).toBeNull();
  });

  it("in the grid, a half-hour block still says who it is, on one line (first iOS pass)", async () => {
    await render(<DayGrid config={servicesConfig} items={items} now={now} date={TODAY} onOpen={noop} onList={noop} t={t} locale="es" />);
    expect(screen.getByText("12:00 · Tomás")).toBeTruthy();
  });

  it("in the grid, each block is a button that says what its row says", async () => {
    const onOpen = jest.fn();
    await render(<DayGrid config={servicesConfig} items={items} now={now} date={TODAY} onOpen={onOpen} onList={noop} t={t} locale="es" />);
    const block = screen.getByLabelText(/11:30, Camila Rojas, Corte y peinado · Javiera Muñoz, Sin confirmar/);
    await fireEvent.press(block);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
    expect(screen.getByText("Javiera")).toBeTruthy();
    expect(screen.getByText("Marcos")).toBeTruthy();
  });
});

describe("Aforo · day (R2.7, R2.8, R2.9)", () => {
  const now = { date: TODAY, minutes: 13 * 60 + 20 };
  const items = [
    res({ id: "in", start: 780, end: 870, partySize: 4, state: "arrived", arrivedAt: "2026-10-22T16:04:00Z", arrivedLocal: "13:04", actions: ["undo"] }),
    res({ id: "late", start: 780, end: 870, partySize: 2, state: "confirmed", customer: { name: "Diego Araya", phone: null }, actions: ["arrived", "noshow"] }),
    res({ id: "soon", start: 810, end: 900, partySize: 6, state: "pending", customer: { name: "Josefa Castillo", phone: null }, actions: ["confirm", "arrived", "cancel"] }),
    res({ id: "later", start: 870, end: 960, partySize: 3, state: "confirmed", actions: ["cancel"] }),
  ];
  const slots = [780, 810, 840, 870, 900].map((time) => ({ date: TODAY, time, inside: time === 810 ? 12 : 6, capacity: 64, blocked: null, closed: false }));

  it("a walk-in who gave no name is «Sin nombre», so the row does not say «Sin reserva» twice (first iOS pass)", async () => {
    const walkin = res({ id: "w", start: 785, end: 875, partySize: 2, state: "arrived", origin: "walkin", channel: "in_person", customer: { name: "", phone: null }, arrivedLocal: "13:05" });
    await render(
      <DayCapacity config={capacityConfig} items={[walkin]} slots={slots} now={now} date={TODAY} slot={null} onSlot={noop} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    expect(screen.getByText("Sin nombre")).toBeTruthy();
    expect(screen.getAllByText("Sin reserva", { includeHiddenElements: true })).toHaveLength(1);
  });

  it("today: inside now, the next hour and the unconfirmed ones", async () => {
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={null} onSlot={noop} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    const figures = screen.getByTestId("capacity-figures");
    expect(within(figures).getByLabelText("Dentro ahora: 6 de 64")).toBeTruthy();
    // 13:30 arrives within the hour (6); 14:30 does not.
    expect(within(figures).getByLabelText("Próxima hora: 6")).toBeTruthy();
    expect(within(figures).getByLabelText("Sin confirmar: 1")).toBeTruthy();
  });

  it("another day: booked, bookings and unconfirmed", async () => {
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date="2026-10-23" slot={null} onSlot={noop} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    expect(screen.getByText("Reservados")).toBeTruthy();
    expect(screen.queryByText("Dentro ahora")).toBeNull();
  });

  it("a slot of the strip filters the day", async () => {
    const onSlot = jest.fn();
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={null} onSlot={onSlot} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    await fireEvent.press(screen.getByLabelText("13:30: 12 de 64 dentro"));
    expect(onSlot).toHaveBeenCalledWith(810);
  });

  it("the slot under way says «Ahora» in its name, and is drawn apart from the chosen one (gate review)", async () => {
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={810} onSlot={noop} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    const current = screen.getByLabelText(/^Ahora, 13:00/);
    const chosen = screen.getByLabelText("13:30: 12 de 64 dentro");
    expect(StyleSheet.flatten(current.props.style).borderStyle).toBe("dashed");
    expect(StyleSheet.flatten(chosen.props.style).borderStyle ?? "solid").toBe("solid");
  });

  it("a slot with nothing says so for that hour, not for the day (gate review)", async () => {
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={900} onSlot={noop} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    expect(screen.queryByText("No hay reservas este día.")).toBeNull();
    expect(screen.getByText("No hay reservas a las 15:00.")).toBeTruthy();
  });

  it("filtered, only that hour, and «Ver todo el día» undoes it", async () => {
    const onSlot = jest.fn();
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={810} onSlot={onSlot} onOpen={noop} onAct={noop} online t={t} locale="es" />,
    );
    expect(screen.queryByTestId("res-in")).toBeNull();
    expect(screen.getByTestId("res-soon")).toBeTruthy();
    await fireEvent.press(screen.getByText("Ver todo el día"));
    expect(onSlot).toHaveBeenCalledWith(null);
  });

  it("offers «Llegó» and «No vino» as the API allows, and says who is late", async () => {
    const onAct = jest.fn();
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={null} onSlot={noop} onOpen={noop} onAct={onAct} online t={t} locale="es" />,
    );
    const late = screen.getByTestId("res-late");
    expect(within(late).getByText("Llega tarde · 20 min")).toBeTruthy();
    await fireEvent.press(within(late).getByText("No vino"));
    expect(onAct).toHaveBeenCalledWith(expect.objectContaining({ id: "late" }), "noshow");
    expect(within(screen.getByTestId("res-soon")).getByText("Llegó")).toBeTruthy();
    expect(within(screen.getByTestId("res-later")).queryByText("Llegó")).toBeNull();
    expect(within(screen.getByTestId("res-in")).getByText("Llegó a las 13:04")).toBeTruthy();
  });

  it("offline, nothing that writes is offered (031 R14.2)", async () => {
    await render(
      <DayCapacity config={capacityConfig} items={items} slots={slots} now={now} date={TODAY} slot={null} onSlot={noop} onOpen={noop} onAct={noop} online={false} t={t} locale="es" />,
    );
    expect(screen.queryByText("No vino")).toBeNull();
  });
});

describe("the screen's states (R16.1, R18.1)", () => {
  it("loading is a skeleton", async () => {
    await render(<ReservasBody state="loading" demo={false} offlineSince={null} partial={false} onRetry={noop} t={t}>{null}</ReservasBody>);
    expect(screen.getByTestId("skeleton")).toBeTruthy();
  });

  it("offline with nothing read yet says so, instead of a skeleton that never ends (gate review)", async () => {
    await render(<ReservasBody state="loading" offline demo={false} offlineSince={null} partial={false} onRetry={noop} t={t}>{null}</ReservasBody>);
    expect(screen.queryByTestId("skeleton")).toBeNull();
    expect(screen.getByText("Sin conexión. Las reservas se cargan cuando vuelva la red.")).toBeTruthy();
  });

  it("failing is an error with «Reintentar»", async () => {
    const onRetry = jest.fn();
    await render(<ReservasBody state="error" demo={false} offlineSince={null} partial={false} onRetry={onRetry} t={t}>{null}</ReservasBody>);
    await fireEvent.press(screen.getByText("Reintentar"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("while another day or week is read, what shows is never the last period's (gate review: a false «no hay reservas»)", () => {
    const { showsOtherPeriod } = require("@/features/reservas/body") as typeof import("@/features/reservas/body");
    expect(showsOtherPeriod({ isPlaceholderData: true }, { isPlaceholderData: false }, false)).toBe(true);
    expect(showsOtherPeriod({ isPlaceholderData: false }, { isPlaceholderData: true }, true)).toBe(true);
    expect(showsOtherPeriod({ isPlaceholderData: false }, { isPlaceholderData: true }, false)).toBe(false);
    expect(showsOtherPeriod({ isPlaceholderData: false }, { isPlaceholderData: false }, true)).toBe(false);
  });

  it("offline says so, partial says what is missing, and the example data says it is an example", async () => {
    await render(
      <ReservasBody state="ready" demo offlineSince="11:02" partial onRetry={noop} t={t}>
        {null}
      </ReservasBody>,
    );
    expect(screen.getByText("Sin conexión. Ves lo último que se cargó.")).toBeTruthy();
    expect(screen.getByText("La ocupación no se pudo cargar; las reservas sí.")).toBeTruthy();
    expect(screen.getByText("Datos de ejemplo")).toBeTruthy();
  });
});
