import { describe, expect, it } from "vitest";

import { NAV } from "@/components/shell/nav";
import { liteNav } from "@/components/shell/lite-nav";
import { t as translate, type MessageKey } from "@/i18n/messages";

import {
  causeKey,
  conversationsAccess,
  countDelta,
  dayColumns,
  deltaText,
  hourColumns,
  metricsPeriods,
  percentText,
  pointsDelta,
  secondsDelta,
  secondsText,
  targetMet,
  todayIn,
  weekdayColumns,
} from "../metrics-model";

/**
 * Spec 083, enmienda del 2026-11-27 (T022) — el modelo de la sección
 * «Conversaciones» de Métricas: el periodo y el anterior (D19), quién la ve
 * (D17 y D18), las diferencias (requisito 12) y las tres gráficas (2.6 y 13.2).
 */

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

describe("el periodo y el anterior (11.6, D19)", () => {
  it("hoy es el día del calendario del cliente, no el de UTC", () => {
    // 2026-11-27 02:00 UTC son las 22:00 del 26 en Caracas.
    expect(todayIn("America/Caracas", new Date("2026-11-27T02:00:00Z"))).toBe("2026-11-26");
    expect(todayIn("No/Existe", new Date("2026-11-27T02:00:00Z"))).toBe("2026-11-27");
  });

  it("los últimos N días hasta hoy, y los N justo antes", () => {
    expect(metricsPeriods(30, "2026-11-27")).toEqual({
      current: { from: "2026-10-29", to: "2026-11-27" },
      previous: { from: "2026-09-29", to: "2026-10-28" },
    });
    expect(metricsPeriods(7, "2026-01-03")).toEqual({
      current: { from: "2025-12-28", to: "2026-01-03" },
      previous: { from: "2025-12-21", to: "2025-12-27" },
    });
  });

  it("con 90 días, los dos periodos caben en los 92 que acepta la API", () => {
    const { current, previous } = metricsPeriods(90, "2026-11-27");
    const days = (p: { from: string; to: string }) => (Date.parse(p.to) - Date.parse(p.from)) / 86_400_000 + 1;
    expect([days(current), days(previous)]).toEqual([90, 90]);
  });
});

describe("quién ve la sección (11.2–11.4, D17 y D18)", () => {
  it("con conversations:read y un cliente, sí; sin cliente, pide uno", () => {
    for (const role of ["owner", "admin", "builder", "analyst"] as const) {
      expect(conversationsAccess(role, "jemma")).toBe("show");
      expect(conversationsAccess(role, "")).toBe("choose");
    }
  });

  it("billing solo ve el dinero: para él la sección no existe", () => {
    expect(conversationsAccess("billing", "jemma")).toBe("hidden");
    expect(conversationsAccess("billing", "")).toBe("hidden");
  });
});

describe("las diferencias frente al periodo anterior (12.1, 12.2, 12.4)", () => {
  it("recuentos en porcentaje; sin nada antes, ninguna", () => {
    expect(countDelta(214, 200)?.kind).toBe("pct");
    expect(countDelta(214, 200)?.value).toBeCloseTo(7);
    expect(countDelta(5, 0)).toBeNull();
    expect(countDelta(5, null)).toBeNull();
  });

  it("porcentajes en puntos y tiempos en segundos; si falta uno, ninguna", () => {
    expect(pointsDelta(76.2, 75)?.value).toBeCloseTo(1.2);
    expect(pointsDelta(null, 75)).toBeNull();
    expect(pointsDelta(76.2, null)).toBeNull();
    expect(secondsDelta(9, 7)).toEqual({ kind: "seconds", value: 2 });
    expect(secondsDelta(9, null)).toBeNull();
  });

  it("se dicen con su signo y su número, sin juicio", () => {
    expect(deltaText(t, { kind: "pct", value: 7 }, "es")).toBe("+7 %");
    expect(deltaText(t, { kind: "pct", value: -16.4 }, "es")).toBe("−16 %");
    expect(deltaText(t, { kind: "points", value: 1.2 }, "es")).toBe("+1,2 puntos");
    expect(deltaText(t, { kind: "points", value: -1 }, "es")).toBe("−1 punto");
    expect(deltaText(t, { kind: "seconds", value: 2 }, "es")).toBe("+2 s");
    expect(deltaText(t, { kind: "pct", value: 0.2 }, "es")).toBe("Igual");
  });
});

describe("las tres gráficas (2.6 y 13.2)", () => {
  it("por día: sin persona abajo y con persona encima, hoy marcado", () => {
    const cols = dayColumns(t, { series: [{ day: "2026-11-26", without_person: 6, with_person: 2 }, { day: "2026-11-27", without_person: 4, with_person: 1 }] }, "2026-11-27");
    expect(cols.map((c) => c.values)).toEqual([[6, 2], [4, 1]]);
    expect(cols[1]).toMatchObject({ label: "Hoy", today: true });
  });

  it("por hora: 24 columnas, con un rótulo cada tres horas para que quepa a 360 px", () => {
    const by_hour = Array.from({ length: 24 }, (_, hour) => ({ hour, without_person: hour, with_person: 0 }));
    const cols = hourColumns({ by_hour });
    expect(cols).toHaveLength(24);
    expect(cols.filter((c) => c.label).map((c) => c.label)).toEqual(["0", "3", "6", "9", "12", "15", "18", "21"]);
    expect(cols[23]).toMatchObject({ title: "23:00–23:59", values: [23, 0] });
    // Sin `today: false`, la gráfica marca la última columna como hoy.
    expect(cols.every((c) => c.today === false)).toBe(true);
  });

  it("por día de la semana: del lunes al domingo, como la API (ISO)", () => {
    const by_weekday = Array.from({ length: 7 }, (_, i) => ({ weekday: i + 1, without_person: 1, with_person: 0 }));
    const cols = weekdayColumns({ by_weekday });
    expect(cols[0]!.title).toBe("Lunes");
    expect(cols[6]!.title).toBe("Domingo");
    expect(cols.every((c) => c.today === false)).toBe(true);
  });
});

describe("las cifras", () => {
  it("el porcentaje con un decimal, o una raya sin datos", () => {
    expect(percentText(t, 76.25, "es")).toBe("76,3 %");
    expect(percentText(t, null, "es")).toBe("—");
  });

  it("el objetivo se alcanza con el mismo número, y sin datos no se juzga", () => {
    expect(targetMet(70, 70)).toBe(true);
    expect(targetMet(69.9, 70)).toBe(false);
    expect(targetMet(null, 70)).toBeNull();
  });

  it("los segundos, como se dicen", () => {
    expect(secondsText(t, 9)).toBe("9 s");
    expect(secondsText(t, 84)).toBe("1 min 24 s");
    expect(secondsText(t, 120)).toBe("2 min");
    expect(secondsText(t, null)).toBe("—");
  });

  it("cada motivo con sus palabras: los de la Bandeja y el freno", () => {
    expect(t(causeKey("booking_brake"))).toBe("Freno de reservas");
    expect(causeKey("no_existe")).toBe("waiting.reason.other");
  });
});

describe("el nombre de la pantalla (11.1, D16)", () => {
  it("la navegación del partner dice «Métricas»; la del cliente sigue en «Consumo»", () => {
    const usage = NAV.flatMap((g) => g.items).find((i) => i.href === "/usage");
    expect(usage?.labelKey).toBe("nav.metrics");
    expect(t("nav.metrics")).toBe("Métricas");
    expect(t(liteNav(["usage"])[0]!.items[0]!.labelKey)).toBe("Consumo");
  });

  it("el buscador y la paleta también dicen «Métricas»", () => {
    expect(t("shell.search.screen.usage")).toBe("Métricas");
    expect(t("cmdk.client.usage")).toBe("Métricas");
  });
});
