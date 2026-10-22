import { fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";

import { capacityConfig, corte, marcos, res, servicesConfig } from "../test/reservas-fixtures";

const { WeekServices, WeekHeat } = require("@/features/reservas/week") as typeof import("@/features/reservas/week");
const { MonthGrid } = require("@/features/reservas/month") as typeof import("@/features/reservas/month");

/**
 * Spec 044, Requisito 3: the week and the month in each mode.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;

describe("Servicios · week (R3.1)", () => {
  const items = [
    res({ id: "a", date: "2026-10-20", start: 600, end: 630, service: corte, pro: marcos }),
    res({ id: "b", date: "2026-10-20", start: 660, end: 690, service: corte, pro: marcos, state: "cancelled" }),
    res({ id: "c", date: "2026-10-22", start: 600, end: 630, service: corte, pro: marcos }),
  ];

  it("a card per day with its count, «Cerrado» on Sunday, and its rows", async () => {
    const onOpen = jest.fn();
    await render(<WeekServices config={servicesConfig} items={items} from="2026-10-19" onOpen={onOpen} onDay={noop} t={t} locale="es" />);
    expect(screen.getByText("Martes, 20 de octubre · 1 reserva")).toBeTruthy();
    expect(screen.getByText("Domingo, 25 de octubre · Cerrado")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("res-c"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "c" }));
  });
});

describe("Aforo · week (R3.2)", () => {
  const slots = ["2026-10-19", "2026-10-20"].flatMap((date) =>
    [780, 810].map((time) => ({ date, time, inside: time === 810 ? 60 : 10, capacity: 64, blocked: date === "2026-10-20" && time === 780 ? "Evento" : null, closed: false })),
  );

  it("is a heat map: each cell says its people, blocked ones say so, and a cell takes you to its day and slot", async () => {
    const onCell = jest.fn();
    await render(<WeekHeat config={capacityConfig} slots={slots} from="2026-10-19" onCell={onCell} t={t} locale="es" />);
    expect(screen.getByText("Comensales dentro a cada hora. Toca una celda para ver sus reservas. Rayado: bloqueado.")).toBeTruthy();
    expect(screen.getByLabelText("Martes, 20 de octubre a las 13:00: bloqueado")).toBeTruthy();
    await fireEvent.press(screen.getByLabelText("Lunes, 19 de octubre a las 13:30: 60 de 64 dentro"));
    expect(onCell).toHaveBeenCalledWith("2026-10-19", 810);
  });

  it("a full slot is light on accentDeep, 5:1 — on primaryDeep it was 4.2 (gate review)", async () => {
    const lightPalette = (require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen")).tokens.light;
    const full = [{ date: "2026-10-19", time: 780, inside: 64, capacity: 64, blocked: null, closed: false }];
    await render(<WeekHeat config={capacityConfig} slots={full} from="2026-10-19" onCell={noop} t={t} locale="es" />);
    const cell = screen.getByLabelText("Lunes, 19 de octubre a las 13:00: 64 de 64 dentro");
    expect(StyleSheet.flatten(cell.props.style).backgroundColor).toBe(lightPalette.accentDeep);
  });

  it("a closed day of the month is not in the faint ink (gate review)", async () => {
    const lightPalette = (require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen")).tokens.light;
    await render(<MonthGrid month="2026-10-15" days={[{ date: "2026-10-04", pct: null, closed: true }]} today="2026-10-22" onDay={noop} t={t} locale="es" />);
    expect(StyleSheet.flatten(screen.getByText("4").props.style).color).not.toBe(lightPalette.subtle);
  });

  it("with large text, an hour of the header shrinks to fit its column instead of breaking «13:0 / 0» (first iOS pass)", async () => {
    await render(<WeekHeat config={capacityConfig} slots={slots} from="2026-10-19" onCell={noop} t={t} locale="es" />);
    expect(screen.getByText("13:00").props).toMatchObject({ numberOfLines: 1, adjustsFontSizeToFit: true });
  });
});

describe("the period switch (first iOS pass)", () => {
  it("with large text, a period shrinks to fit instead of breaking «Seman / a»", async () => {
    const { Segmented } = require("@/ui/bits") as typeof import("@/ui/bits");
    await render(<Segmented label="Periodo" value="week" onChange={noop} options={[{ value: "day", label: "Día" }, { value: "week", label: "Semana" }, { value: "month", label: "Mes" }]} />);
    expect(screen.getByText("Semana").props).toMatchObject({ numberOfLines: 1, adjustsFontSizeToFit: true });
  });
});

describe("the month (R3.3)", () => {
  const days = [
    { date: "2026-10-01", pct: 40, closed: false },
    { date: "2026-10-04", pct: null, closed: true },
    { date: "2026-10-22", pct: 72, closed: false },
  ];

  it("starts on Monday, says each day's % or «Cerrado», and a day takes you to it", async () => {
    const onDay = jest.fn();
    await render(<MonthGrid month="2026-10-15" days={days} today="2026-10-22" onDay={onDay} t={t} locale="es" />);
    // The weekday letters are for the eye; each day says its whole name to the screen reader.
    expect(screen.getAllByText("L", { includeHiddenElements: true })).toHaveLength(1);
    expect(screen.getByLabelText("Domingo, 4 de octubre: cerrado")).toBeTruthy();
    await fireEvent.press(screen.getByLabelText("Jueves, 22 de octubre: 72 % ocupado"));
    expect(onDay).toHaveBeenCalledWith("2026-10-22");
  });

  it("«Cerrado» shrinks to fit a seventh of the phone instead of becoming «Cerra…» (first iOS pass)", async () => {
    await render(<MonthGrid month="2026-10-15" days={days} today="2026-10-22" onDay={jest.fn()} t={t} locale="es" />);
    const closed = screen.getByText("Cerrado", { includeHiddenElements: true });
    expect(closed.props).toMatchObject({ numberOfLines: 1, adjustsFontSizeToFit: true });
  });
});
