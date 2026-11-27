import { describe, expect, it } from "vitest";

import { t as translate, type MessageKey } from "@/i18n/messages";
import type { ClientReport } from "@/lib/backend/client-report";

import {
  addDays,
  causeKey,
  defaultPeriod,
  lastDays,
  percentText,
  periodProblem,
  presetOf,
  readPeriod,
  reportColumns,
  reportHref,
  secondsText,
  targetMet,
  todayIn,
} from "../report-model";

/**
 * Spec 083 (T006) — las cuentas puras del informe: el periodo por defecto (30
 * días hasta hoy en la zona del cliente, 1.4), las fechas que no se pueden pedir
 * (1.5), las columnas de la gráfica (2.6) y cómo se escriben las cifras.
 */

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

describe("hoy y el periodo por defecto, en la zona del cliente", () => {
  // 03:30 UTC del 13 son las 23:30 del 12 en Caracas.
  const now = new Date("2026-11-13T03:30:00Z");

  it("hoy es el día del calendario del cliente, no el de UTC", () => {
    expect(todayIn("America/Caracas", now)).toBe("2026-11-12");
    expect(todayIn("UTC", now)).toBe("2026-11-13");
  });

  it("una zona que no existe cuenta como UTC, como la API", () => {
    expect(todayIn("Mars/Olympus", now)).toBe("2026-11-13");
  });

  it("sin periodo, los últimos 30 días con hoy incluido", () => {
    expect(defaultPeriod("America/Caracas", now)).toEqual({ from: "2026-10-14", to: "2026-11-12" });
  });

  it("los atajos cuentan hoy", () => {
    expect(lastDays(7, "2026-11-12")).toEqual({ from: "2026-11-06", to: "2026-11-12" })
    expect(presetOf({ from: "2026-11-06", to: "2026-11-12" }, "2026-11-12")).toBe(7);
    expect(presetOf({ from: "2026-11-05", to: "2026-11-12" }, "2026-11-12")).toBeNull();
    // Un periodo que no acaba hoy no es un atajo, aunque mida 7 días.
    expect(presetOf({ from: "2026-11-01", to: "2026-11-07" }, "2026-11-12")).toBeNull();
  });

  it("sumar días cruza meses y años", () => {
    expect(addDays("2026-12-30", 3)).toBe("2027-01-02");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("las fechas que no se pueden pedir (1.5)", () => {
  const today = "2026-11-26";

  it("al revés, más de 92 días o después de hoy", () => {
    expect(periodProblem({ from: "2026-11-10", to: "2026-11-09" }, today)).toBe("range_reversed");
    expect(periodProblem({ from: "2026-08-26", to: "2026-11-26" }, today)).toBe("range_too_long");
    expect(periodProblem({ from: "2026-11-20", to: "2026-11-27" }, today)).toBe("range_in_future");
    expect(periodProblem({ from: "2026-13-01", to: "2026-11-27" }, today)).toBe("invalid");
  });

  it("92 días justos sí, y un solo día también", () => {
    expect(periodProblem({ from: "2026-08-27", to: "2026-11-26" }, today)).toBeNull();
    expect(periodProblem({ from: today, to: today }, today)).toBeNull();
  });

  it("la dirección manda; si no vale, el periodo por defecto", () => {
    const now = new Date("2026-11-26T15:00:00Z");
    expect(readPeriod({ from: "2026-11-10", to: "2026-11-20" }, "UTC", now)).toEqual({ from: "2026-11-10", to: "2026-11-20" });
    expect(readPeriod({ from: "2026-11-10", to: "2026-12-20" }, "UTC", now)).toEqual({ from: "2026-10-28", to: "2026-11-26" });
    expect(readPeriod({ from: ["a", "b"] }, "UTC", now)).toEqual({ from: "2026-10-28", to: "2026-11-26" });
  });

  it("el enlace lleva el periodo, para recargar o compartir el mismo informe (1.3)", () => {
    expect(reportHref("jemma hair", { from: "2026-11-10", to: "2026-12-07" })).toBe(
      "/clients/jemma%20hair/report?from=2026-11-10&to=2026-12-07",
    );
  });
});

const SERIES: ClientReport["conversations"]["series"] = [
  { day: "2026-11-24", without_person: 3, with_person: 1 },
  { day: "2026-11-25", without_person: 0, with_person: 0 },
  { day: "2026-11-26", without_person: 2, with_person: 2 },
];

describe("la gráfica por día (2.6)", () => {
  it("una columna por día, resueltas sin persona abajo y con persona encima", () => {
    const cols = reportColumns(t, { series: SERIES }, "2026-11-26");
    expect(cols.map((c) => c.values)).toEqual([
      [3, 1],
      [0, 0],
      [2, 2],
    ]);
    expect(cols.map((c) => c.key)).toEqual(["2026-11-24", "2026-11-25", "2026-11-26"]);
    expect(cols[0]!.title).toBe("Martes, 24 nov");
  });

  it("hoy se marca solo si el periodo llega a hoy", () => {
    expect(reportColumns(t, { series: SERIES }, "2026-11-26").map((c) => c.today)).toEqual([false, false, true]);
    expect(reportColumns(t, { series: SERIES }, "2026-11-30").map((c) => c.today)).toEqual([false, false, false]);
  });
});

describe("las cifras", () => {
  it("el porcentaje con una cifra decimal, o una raya sin datos", () => {
    expect(percentText(t, 76.2, "es")).toBe("76,2 %");
    expect(percentText(t, 70, "es")).toBe("70 %");
    expect(percentText(t, null, "es")).toBe("—");
  });

  it("el objetivo se alcanza con el mismo número, y sin datos no se juzga", () => {
    expect(targetMet(70, 70)).toBe(true);
    expect(targetMet(69.9, 70)).toBe(false);
    expect(targetMet(null, 70)).toBeNull();
  });

  it("los segundos, como se dicen", () => {
    expect(secondsText(t, 9)).toBe("9 s");
    expect(secondsText(t, 70)).toBe("1 min 10 s");
    expect(secondsText(t, 120)).toBe("2 min");
    expect(secondsText(t, null)).toBe("—");
  });

  it("cada motivo con sus palabras: los de la Bandeja y el freno", () => {
    expect(t(causeKey("no_balance"))).toBe("Sin saldo");
    expect(t(causeKey("escalated"))).toBe("Pidió una persona");
    expect(t(causeKey("booking_brake"))).toBe("Freno de reservas");
    expect(t(causeKey("other"))).toBe("Otro motivo");
  });
});
