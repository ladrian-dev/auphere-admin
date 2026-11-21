import { fireEvent, render, screen } from "@testing-library/react-native";

import { t as translate, type T } from "@/i18n/t";

import { servicesConfig, TODAY } from "../test/reservas-fixtures";

const { price } = require("@/features/reservas/format") as typeof import("@/features/reservas/format");
const { phoneProblem } = require("@/features/reservas/phone") as typeof import("@/features/reservas/phone");
const { calendarText } = require("@/features/reservas/format") as typeof import("@/features/reservas/format");
const { toConfig } = require("@/api/reservas") as typeof import("@/api/reservas");
const { NewReservationForm } = require("@/features/reservas/new-reservation") as typeof import("@/features/reservas/new-reservation");
const { ReservasSettings } = require("@/features/reservas/settings") as typeof import("@/features/reservas/settings");

/**
 * Spec 069, Fase 3 (T022, T023) and Requisito 13.7: three things the app said
 * wrong, each red before its fix.
 */
const t: T = (k, v) => translate("es", k, v);
const en: T = (k, v) => translate("en", k, v);
const noop = () => undefined;

describe("a service's price comes in minor units, with the currency's decimals (R14.4, R21.1)", () => {
  it("CLP has no decimals: 18000 is $18.000", () => {
    expect(price(18000, "CLP", "es")).toBe("$18.000");
  });

  it("EUR and USD have two: 1850 is 18,50, never 1.850", () => {
    expect(price(1850, "EUR", "es")).toMatch(/^18,50\s€$/);
    expect(price(1850, "USD", "en")).toBe("$18.50");
    expect(price(1850, "EUR", "en")).toBe("€18.50");
  });

  it("a currency Intl does not know still says its number and code", () => {
    expect(price(1850, "XYZ1", "es")).toMatch(/18,50 XYZ1/);
  });
});

describe("the phone of a booking made by hand is required and valid (spec 064 R3, R15.1)", () => {
  it("says what is wrong, as the web does", () => {
    expect(phoneProblem("")).toBe("required");
    expect(phoneProblem("   ")).toBe("required");
    expect(phoneProblem("56 9 1234 5678")).toBe("prefix");
    expect(phoneProblem("+56 9 1234 5678x")).toBe("chars");
    expect(phoneProblem("+56 91")).toBe("length");
    expect(phoneProblem("+56 9 1234 5678")).toBeNull();
    expect(phoneProblem("+34 (612) 34-56-78")).toBeNull();
  });

  const free = [{ time: 17 * 60, pro: { id: "p-marcos", name: "Marcos Soto" }, left: null, full: false }];

  it("«Guardar» without a phone says the field is required and saves nothing (Historia 5, scenario 2)", async () => {
    const onSave = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={noop} onSave={onSave} saving={false} error={null} online t={t} locale="es" />,
    );
    await fireEvent.press(screen.getByLabelText("17:00 con Marcos Soto"));
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Lucía Fernández");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar reserva" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el teléfono de quien reserva.")).toBeTruthy();
  });

  it("a phone without its country prefix is refused, with the reason", async () => {
    const onSave = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={noop} onSave={onSave} saving={false} error={null} online t={t} locale="es" />,
    );
    await fireEvent.press(screen.getByLabelText("17:00 con Marcos Soto"));
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Lucía Fernández");
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "961234567");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar reserva" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el teléfono con el prefijo del país, como +56 9 1234 5678.")).toBeTruthy();
  });

  it("with a valid phone it saves it with the booking", async () => {
    const onSave = jest.fn();
    await render(
      <NewReservationForm config={servicesConfig} today={TODAY} initialDate={TODAY} slots={free} slotsLoading={false} onQuery={noop} onSave={onSave} saving={false} error={null} online t={t} locale="es" />,
    );
    await fireEvent.press(screen.getByLabelText("17:00 con Marcos Soto"));
    await fireEvent.changeText(screen.getByLabelText("Nombre y apellido"), "Lucía Fernández");
    await fireEvent.changeText(screen.getByLabelText("Teléfono"), "+56 9 6123 4567");
    await fireEvent.press(screen.getByRole("button", { name: "Guardar reserva" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ customer: { name: "Lucía Fernández", phone: "+56 9 6123 4567" } }));
  });
});

describe("the real state of each professional's Google calendar (R13.7)", () => {
  const settings = {
    mode: "services",
    timezone: "America/Santiago",
    currency: "CLP",
    business_hours: { monday: [{ from: "09:00", to: "19:00" }] },
    waitlist: { enabled: true, lead_minutes: 120 },
    confirmation: { enabled: true, when: "24h" },
    version: 4,
  };
  const member = (id: string, status: string, busy = false) => ({ id, name: id, calendar: { status, business_busy: busy } });

  it("keeps every state the API says, not only «connected» or «none»", () => {
    const c = toConfig(
      settings,
      [member("a", "connected"), member("b", "pending", true), member("c", "needs_calendar"), member("d", "needs_reauth"), member("e", "error"), member("f", "none")],
      [],
      null,
    );
    // `calendar` keeps saying connected or not; the state says the rest.
    expect(c.services?.team.map((p) => p.calendarState ?? (p.calendar === "google" ? "connected" : "none"))).toEqual(["connected", "pending", "needs_calendar", "needs_reauth", "error", "none"]);
    expect(c.services?.team.map((p) => p.calendar)).toEqual(["google", "none", "none", "none", "none", "none"]);
    expect(c.services?.team[1]?.calendarBusy).toBe(true);
  });

  it("says each one in its own words, in Spanish and in English", () => {
    const p = (calendarState: "connected" | "pending" | "needs_calendar" | "needs_reauth" | "error" | "none", calendarBusy = false) => ({
      id: "x",
      name: "X",
      calendar: calendarState === "connected" ? ("google" as const) : ("none" as const),
      calendarState,
      calendarBusy,
    });
    expect(calendarText(p("connected"), t)).toBe("Google Calendar conectado");
    expect(calendarText(p("none"), t)).toBe("Sin calendario conectado");
    expect(calendarText(p("pending"), t)).toBe("Esperando a que autorice en Google");
    expect(calendarText(p("needs_calendar"), t)).toBe("Falta elegir qué calendario usar");
    expect(calendarText(p("needs_reauth"), t)).toBe("Hay que volver a conectar su calendario");
    expect(calendarText(p("error"), t)).toBe("No pudimos sincronizar su calendario");
    expect(calendarText(p("pending", true), t)).toBe("Esperando a que autorice en Google · Algunas horas siguen bloqueadas por el Google del negocio");
    expect(calendarText(p("needs_reauth"), en)).toBe("Their calendar needs connecting again");
  });

  it("a team without the new field reads as before (the API's «google» or «none»)", () => {
    expect(calendarText({ id: "x", name: "X", calendar: "google" }, t)).toBe("Google Calendar conectado");
    expect(calendarText({ id: "x", name: "X", calendar: "none" }, t)).toBe("Sin calendario conectado");
  });

  it("Ajustes de reservas shows the real state of each member", async () => {
    const team = [
      { id: "p-javiera", name: "Javiera Muñoz", calendar: "google" as const, calendarState: "connected" as const },
      { id: "p-marcos", name: "Marcos Soto", calendar: "none" as const, calendarState: "needs_reauth" as const },
    ];
    const config = { ...servicesConfig, services: { ...servicesConfig.services!, team } };
    await render(<ReservasSettings config={config} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    expect(screen.getByLabelText("Marcos Soto. Hay que volver a conectar su calendario")).toBeTruthy();
    expect(screen.getByLabelText("Javiera Muñoz. Google Calendar conectado")).toBeTruthy();
  });

  it("and the price of a service in euros, with its cents", async () => {
    const config = { ...servicesConfig, currency: "EUR" };
    await render(<ReservasSettings config={config} online saving={false} onPatch={noop} onUnblock={noop} onBlock={noop} t={t} locale="es" />);
    // The fixture keeps 12000 in minor units: in euros that is 120,00 €, not 12.000 €.
    expect(screen.getByLabelText(/^Corte: 30 min · 120,00\s€$/)).toBeTruthy();
  });
});
