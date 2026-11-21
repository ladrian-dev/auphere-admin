import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { corte, javiera, marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

const { DayHeader } = require("@/features/reservas/header") as typeof import("@/features/reservas/header");
const { DayServices } = require("@/features/reservas/day-services") as typeof import("@/features/reservas/day-services");
const { DayGrid } = require("@/features/reservas/day-grid") as typeof import("@/features/reservas/day-grid");
const { WaitlistCard } = require("@/features/reservas/waitlist-card") as typeof import("@/features/reservas/waitlist-card");
const model = require("@/lib/reservas-model") as typeof import("@/lib/reservas-model");
const { tokens } = require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen");

/**
 * Spec 069, Requisito 13 (design §4): the day of Reservas — the strip, the
 * cards, the grid with its free time — and what the day leads to.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const light = tokens.light;
const now = { date: TODAY, minutes: 11 * 60 + 20 };

describe("the strip of days (R13.1)", () => {
  it("is the week of the chosen day, today in turquoise without a circle, the chosen one in ink", async () => {
    await render(
      <DayHeader period="day" onPeriod={noop} date="2026-10-23" today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />,
    );
    // Monday 19 to Sunday 25 October.
    expect(screen.getByTestId("strip-2026-10-19")).toBeTruthy();
    expect(screen.getByTestId("strip-2026-10-25")).toBeTruthy();
    expect(screen.queryByTestId("strip-2026-10-26")).toBeNull();
    const today = screen.getByLabelText("Jueves, 22 de octubre, hoy");
    expect(StyleSheet.flatten(today.props.style).backgroundColor).toBe("transparent");
    expect(StyleSheet.flatten(within(today).getByText("22").props.style).color).toBe(light.highlightInk);
    expect(within(today).getByText("hoy")).toBeTruthy();
    const chosen = screen.getByLabelText("Viernes, 23 de octubre");
    expect(StyleSheet.flatten(chosen.props.style).backgroundColor).toBe(light.selection);
  });

  it("marks the days with bookings with a dot", async () => {
    await render(
      <DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} marks={new Set(["2026-10-20"])} t={t} locale="es" />,
    );
    expect(screen.getByTestId("strip-dot-2026-10-20")).toBeTruthy();
    expect(screen.queryByTestId("strip-dot-2026-10-21")).toBeNull();
  });

  it("changes the week from each day by the screen reader's actions too (R3.4)", async () => {
    const onDate = jest.fn();
    await render(
      <DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={onDate} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />,
    );
    const day = screen.getByLabelText("Jueves, 22 de octubre, hoy");
    expect(day.props.accessibilityActions.map((a: { label: string }) => a.label)).toEqual(["Semana anterior", "Semana siguiente"]);
    await fireEvent(day, "accessibilityAction", { nativeEvent: { actionName: "nextWeek" } });
    expect(onDate).toHaveBeenLastCalledWith("2026-10-29");
    await fireEvent(day, "accessibilityAction", { nativeEvent: { actionName: "previousWeek" } });
    expect(onDate).toHaveBeenLastCalledWith("2026-10-15");
  });

  it("list or grid is one choice named «Vista», each option said", async () => {
    const onView = jest.fn();
    await render(<DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={onView} t={t} locale="es" />);
    expect(screen.getByLabelText("Vista")).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Lista" }).props.accessibilityState).toMatchObject({ checked: true });
    await fireEvent.press(screen.getByRole("radio", { name: "Cuadrícula" }));
    expect(onView).toHaveBeenCalledWith("grid");
  });
});

describe("the day as cards (R13.2)", () => {
  const items = [
    res({ id: "a", start: 600, end: 630, service: corte, pro: marcos, state: "confirmed" }),
    res({ id: "b", start: 690, end: 735, service: peinado, pro: javiera, state: "pending", customer: { name: "Camila Rojas", phone: null } }),
    res({ id: "c", start: 780, end: 810, service: corte, pro: marcos, state: "cancelled", customer: { name: "Tomás Silva", phone: null } }),
  ];

  it("one card per reservation in its state's soft colour, the state in words", async () => {
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(StyleSheet.flatten(screen.getByTestId("res-b").props.style).backgroundColor).toBe(light.warningBg);
    expect(within(screen.getByTestId("res-b")).getByText("Sin confirmar")).toBeTruthy();
    // Cancelled: sunken, its name struck through — and said in words, never colour alone.
    expect(StyleSheet.flatten(within(screen.getByTestId("res-c")).getByText("Tomás Silva").props.style).textDecorationLine).toBe("line-through");
    expect(within(screen.getByTestId("res-c")).getByText("Cancelada")).toBeTruthy();
  });

  it("«Ahora» is the brand's green, not red: red is for errors", async () => {
    await render(<DayServices config={servicesConfig} items={items} now={now} date={TODAY} pro={null} onPro={noop} onOpen={noop} t={t} locale="es" />);
    expect(StyleSheet.flatten(screen.getByText("Ahora · 11:20").props.style).color).toBe(light.highlightInk);
  });

  it("an empty day ahead offers to book it; a past one does not", async () => {
    const onNew = jest.fn();
    await render(<DayServices config={servicesConfig} items={[]} now={now} date="2026-10-23" pro={null} onPro={noop} onOpen={noop} onNew={onNew} t={t} locale="es" />);
    expect(screen.getByText("El agente llena los huecos libres cuando alguien escribe. También puedes reservar tú.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Reservar este día" }));
    expect(onNew).toHaveBeenCalledWith("2026-10-23");
    await render(<DayServices config={servicesConfig} items={[]} now={now} date="2026-10-20" pro={null} onPro={noop} onOpen={noop} onNew={onNew} t={t} locale="es" />);
    expect(screen.queryByRole("button", { name: "Reservar este día" })).toBeNull();
  });

  it("a closed day offers the next open one", async () => {
    const onDay = jest.fn();
    await render(<DayServices config={servicesConfig} items={[]} now={now} date="2026-10-25" pro={null} onPro={noop} onOpen={noop} onDay={onDay} t={t} locale="es" />);
    await fireEvent.press(screen.getByRole("button", { name: "Ver el lun 26" }));
    expect(onDay).toHaveBeenCalledWith("2026-10-26");
  });
});

describe("the grid (R13.2–R13.4)", () => {
  const items = [
    res({ id: "a", start: 600, end: 645, service: peinado, pro: marcos, state: "confirmed", customer: { name: "Diego Ramírez", phone: null } }),
    res({ id: "b", start: 630, end: 660, service: corte, pro: javiera, state: "pending", customer: { name: "Lucía Fernández", phone: null } }),
  ];

  it("draws the ones at the same time side by side", async () => {
    await render(<DayGrid config={servicesConfig} items={items} now={now} date={TODAY} onOpen={noop} onList={noop} t={t} locale="es" />);
    const a = StyleSheet.flatten(screen.getByTestId("block-a").parent?.props.style);
    const b = StyleSheet.flatten(screen.getByTestId("block-b").parent?.props.style);
    expect([a.left, a.width]).toEqual(["0%", "50%"]);
    expect([b.left, b.width]).toEqual(["50%", "50%"]);
  });

  it("a free band books that day and time (R13.3), with the person chosen", async () => {
    const onFree = jest.fn();
    const friday = [res({ id: "f", date: "2026-10-23", start: 600, end: 645, service: peinado, pro: marcos }), res({ id: "g", date: "2026-10-23", start: 540, end: 570, service: corte, pro: javiera })];
    await render(<DayGrid config={servicesConfig} items={friday} now={now} date="2026-10-23" pro="p-marcos" onFree={onFree} onOpen={noop} onList={noop} t={t} locale="es" />);
    // Marcos's day: Javiera's 9:00 does not take his time; his own 10:00 does.
    expect(screen.getByLabelText("Libre de 11:00 a 19:00. Reservar")).toBeTruthy();
    await fireEvent.press(screen.getByLabelText("Libre de 09:00 a 10:00. Reservar"));
    expect(onFree).toHaveBeenCalledWith("2026-10-23", 540, "p-marcos");
  });

  it("offers no free time in the past, nor inside the agent's notice (R13.4)", async () => {
    const onFree = jest.fn();
    await render(<DayGrid config={servicesConfig} items={[]} now={now} date={TODAY} onFree={onFree} onOpen={noop} onList={noop} t={t} locale="es" />);
    // 11:20 plus the agent's 60 minutes: the first free time is 12:30.
    expect(screen.getByLabelText("Libre de 12:30 a 19:00. Reservar")).toBeTruthy();
    expect(screen.queryByTestId("free-09:00")).toBeNull();
    await render(<DayGrid config={servicesConfig} items={[]} now={now} date="2026-10-21" onFree={onFree} onOpen={noop} onList={noop} t={t} locale="es" />);
    expect(screen.queryAllByLabelText(/^Libre de/)).toHaveLength(0);
  });

  it("only the open hours, the break said in words", async () => {
    const split = { ...servicesConfig, hours: [{ weekday: 4 as const, open: 540, close: 840 }, { weekday: 4 as const, open: 960, close: 1140 }] };
    await render(<DayGrid config={split} items={[]} now={now} date={TODAY} onOpen={noop} onList={noop} t={t} locale="es" />);
    expect(screen.getByText("Cerrado de 14:00 a 16:00")).toBeTruthy();
    expect(screen.getByTestId("grid-span-09:00")).toBeTruthy();
    expect(screen.getByTestId("grid-span-16:00")).toBeTruthy();
  });

  it("a pending block shows its clock, not only a colour (design finding 2)", async () => {
    await render(<DayGrid config={servicesConfig} items={items} now={now} date={TODAY} onOpen={noop} onList={noop} t={t} locale="es" />);
    expect(screen.getByLabelText(/Lucía Fernández, Corte · Javiera Muñoz, Sin confirmar/)).toBeTruthy();
  });
});

describe("the pure rules behind it", () => {
  it("the notice reaches into tomorrow", () => {
    expect(model.earliestFrom({ date: TODAY, minutes: 23 * 60 }, 1440)).toEqual({ date: "2026-10-23", minutes: 23 * 60 });
    expect(model.earliestFrom({ date: TODAY, minutes: 23 * 60 + 30 }, 60)).toEqual({ date: "2026-10-23", minutes: 30 });
  });

  it("free bands skip what is booked and merge the rest", () => {
    const bands = model.freeBands([{ open: 540, close: 720 }], [{ start: 600, end: 660 }], 30, "2026-10-23", { date: TODAY, minutes: 0 });
    expect(bands).toEqual([
      { from: 540, to: 600 },
      { from: 660, to: 720 },
    ]);
  });
});

describe("the waitlist card after the bookings (design §4.1)", () => {
  it("says how many wait and who, and opens the list", async () => {
    const onPress = jest.fn();
    const w = (id: string, name: string) => ({ id, name, phone: null, wants: { date: null, time: null, partySize: null, service: null, pro: null, text: null }, state: "waiting" as const, fits: null, offeredUntil: null, joinedBy: "agent" as const, by: null, joinedAt: "" });
    await render(<WaitlistCard items={[w("1", "Raúl Ortega"), w("2", "Inés Navarro")]} onPress={onPress} t={t} />);
    expect(screen.getByText("2 personas · Raúl, Inés")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("waitlist-card"));
    expect(onPress).toHaveBeenCalled();
  });
});
