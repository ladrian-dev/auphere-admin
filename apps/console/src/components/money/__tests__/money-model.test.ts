import { describe, expect, it } from "vitest";

import { t as translate } from "@/i18n/messages";
import type { MessageKey } from "@/i18n/messages";
import type { Receipt, UsageDaily } from "@/lib/backend/money-types";

import {
  assignPreview,
  assignedText,
  buildShare,
  chartColumns,
  chartLines,
  chartTable,
  chartTotal,
  convertMicros,
  daysText,
  eurUsdOf,
  fxLine,
  migrationAdjust,
  migrationPending,
  missingOf,
  money,
  moneyErrorText,
  moneyText,
  noteProblem,
  parseAmount,
  parseDays,
  parseLine,
  proposalTotals,
  receiptFxLine,
  rechargeHref,
  requestedText,
  units,
} from "../money-model";

/**
 * Spec 047 (T159, T153): las cuentas puras del dinero. Leer un importe con
 * coma, escribirlo en `es-ES` (miles, dos decimales, el símbolo detrás, saldos
 * hacia abajo), el cambio del BCE, el recibo con «Faltan» y el aviso ámbar, y
 * la tabla de la gráfica de bloques.
 */
const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const EUR = (n: number) => money(units(n), "EUR");
const USD = (n: number) => money(units(n), "USD");
/** Los espacios de `Intl` (duros y finos) como espacios normales, para comparar. */
const plain = (s: string) => s.replace(/[  ]/g, " ");

describe("parseAmount · «Otra cantidad» admite coma decimal (45.2)", () => {
  it("coma y punto decimales, con uno o dos decimales", () => {
    expect(parseAmount("12,5")).toEqual({ kind: "ok", micros: 1_250_000 });
    expect(parseAmount("12,50")).toEqual({ kind: "ok", micros: 1_250_000 });
    expect(parseAmount("12.05")).toEqual({ kind: "ok", micros: 1_205_000 });
    expect(parseAmount(" 20 ")).toEqual({ kind: "ok", micros: 2_000_000 });
  });

  it("los puntos de miles de es-ES, con o sin decimales", () => {
    expect(parseAmount("1.234,50")).toEqual({ kind: "ok", micros: 123_450_000 });
    expect(parseAmount("1.234")).toEqual({ kind: "ok", micros: 123_400_000 });
    expect(parseAmount("12.345.678")).toEqual({ kind: "invalid" });
  });

  it("vacío no es cero, y lo que no es un importe tampoco", () => {
    expect(parseAmount("")).toEqual({ kind: "empty" });
    expect(parseAmount("   ")).toEqual({ kind: "empty" });
    expect(parseAmount("0")).toEqual({ kind: "ok", micros: 0 });
    for (const bad of ["-5", "12,505", "abc", "1,2,3", "€20", "1e3"]) expect(parseAmount(bad), bad).toEqual({ kind: "invalid" });
  });
})

describe("moneyText · es-ES (45.9, 43.10)", () => {
  it("dos decimales, separador de miles y el símbolo detrás: «1.234,50 €» y «60,00 USD»", () => {
    expect(plain(moneyText(EUR(1234.5)))).toBe("1.234,50 €");
    expect(plain(moneyText(USD(60)))).toBe("60,00 USD");
    expect(plain(moneyText(EUR(1_000_000)))).toBe("1.000.000,00 €");
  });

  it("los saldos se redondean hacia abajo y el gasto al céntimo más cercano", () => {
    const value = money(1_234_567, "EUR"); // 12,34567 €
    expect(plain(moneyText(value, "down"))).toBe("12,34 €");
    expect(plain(moneyText(value))).toBe("12,35 €");
    expect(plain(moneyText(money(1_234_000, "USD"), "down"))).toBe("12,34 USD");
  });

  it("sin importe, una raya", () => {
    expect(moneyText(null)).toBe("—");
  });
});

describe("el cambio del BCE", () => {
  it("siempre se dice como euros a dólares, venga como venga", () => {
    expect(eurUsdOf("1.0852", "EUR", "USD")).toBeCloseTo(1.0852, 6);
    expect(eurUsdOf(String(1 / 1.0852), "USD", "EUR")).toBeCloseTo(1.0852, 6);
    expect(eurUsdOf("1", "EUR", "EUR")).toBeNull();
    expect(eurUsdOf("nope", "EUR", "USD")).toBeNull();
  });

  it("convierte con el euro como base", () => {
    expect(convertMicros(units(20), "USD", "EUR", 1.0852)).toBe(Math.round(units(20) / 1.0852));
    expect(convertMicros(units(10), "EUR", "USD", 1.0852)).toBe(units(10.852));
    expect(convertMicros(123, "EUR", "EUR", 1.0852)).toBe(123);
  });

  it("«1 € = 1,0852 USD · BCE 26 oct 2026»", () => {
    expect(fxLine(t, 1.0852, "2026-10-26")).toBe("1 € = 1,0852 USD · BCE 26 oct 2026");
    expect(fxLine(t, 1.08, "2026-10-26")).toBe("1 € = 1,08 USD · BCE 26 oct 2026");
    expect(fxLine(t, 1.08, null)).toBe("1 € = 1,08 USD · BCE");
  });
});

describe("el recibo de «Asignar saldo»", () => {
  it("misma moneda: lo que sale es lo que entra, y lo que queda en la cuenta", () => {
    const p = assignPreview({ amountMicros: units(20), bag: USD(15.5), available: USD(241.48), eurUsd: null })!;
    expect(plain(moneyText(p.before))).toBe("15,50 USD");
    expect(plain(moneyText(p.assigned))).toBe("20,00 USD");
    expect(plain(moneyText(p.debit))).toBe("20,00 USD");
    expect(plain(moneyText(p.after))).toBe("35,50 USD");
    expect(plain(moneyText(p.left))).toBe("221,48 USD");
    expect(p.missing).toBeNull();
    expect(p.lowAccount).toBe(false);
    expect(p.eurUsd).toBeNull();
  });

  it("monedas distintas: sale de la cuenta en su moneda, al cambio del día", () => {
    const p = assignPreview({ amountMicros: units(20), bag: USD(15.5), available: EUR(240), eurUsd: 1.0852 })!;
    expect(plain(moneyText(p.debit))).toBe("18,43 €");
    expect(plain(moneyText(p.left, "down"))).toBe("221,57 €");
    expect(p.eurUsd).toBe(1.0852);
  });

  it("sin el cambio del día no hay vista previa (la API tampoco deja asignar)", () => {
    expect(assignPreview({ amountMicros: units(20), bag: USD(0), available: EUR(100), eurUsd: null })).toBeNull();
  });

  it("si no llega: «Faltan» en la moneda de la cuenta, y no avisa en ámbar (45.3)", () => {
    const p = assignPreview({ amountMicros: units(50), bag: EUR(0), available: EUR(30), eurUsd: null })!;
    expect(p.missing && plain(moneyText(p.missing))).toBe("20,00 €");
    expect(p.lowAccount).toBe(false);
    expect(plain(moneyText(p.left))).toBe("0,00 €");
    expect(plain(t("money.receipt.missing", { amount: moneyText(p.missing) }))).toBe("Faltan 20,00 €");
  });

  it("si la cuenta se queda con menos del 20 % de lo que tenía: ámbar, sin bloquear (45.4)", () => {
    expect(assignPreview({ amountMicros: units(81), bag: EUR(0), available: EUR(100), eurUsd: null })!.lowAccount).toBe(true);
    expect(assignPreview({ amountMicros: units(80), bag: EUR(0), available: EUR(100), eurUsd: null })!.lowAccount).toBe(false);
    expect(assignPreview({ amountMicros: units(100), bag: EUR(0), available: EUR(100), eurUsd: null })!.lowAccount).toBe(true);
  });

  it("«Recargar mi cuenta» lleva a comprar lo que falta, redondeado hacia arriba", () => {
    expect(rechargeHref(money(2_000_001, "EUR"))).toBe("/billing?recargar=21");
    expect(rechargeHref(EUR(20))).toBe("/billing?recargar=20");
  });

  it("el aviso final dice lo asignado y lo que queda (45.5)", () => {
    const receipt: Receipt = {
      client_balance_before: USD(15.5),
      assigned: USD(20),
      debited_from_account: EUR(18.43),
      fx: { rate: "1.0852", date: "2026-10-26", source: "ECB" },
      client_balance_after: USD(35.5),
      account_left: EUR(221.48),
      warn_low_account: false,
    };
    expect(plain(assignedText(t, receipt, "Flor y Encanto"))).toBe("Asignados 20,00 USD a Flor y Encanto. En tu cuenta quedan 221,48 €.");
    expect(receiptFxLine(t, receipt)).toBe("1 € = 1,0852 USD · BCE 26 oct 2026");
    // Cuenta en dólares y bolsa en euros: la API manda el cambio de USD a EUR.
    expect(receiptFxLine(t, { ...receipt, debited_from_account: USD(21.7), assigned: EUR(20), fx: { rate: String(1 / 1.0852), date: "2026-10-26", source: "ECB" } })).toBe(
      "1 € = 1,0852 USD · BCE 26 oct 2026",
    );
    expect(receiptFxLine(t, { ...receipt, debited_from_account: USD(20) })).toBeNull();
  });

  it("lo que falta según la API (409 insufficient_account)", () => {
    const res = { ok: false as const, status: 409, message: "", code: "insufficient_account", info: { available_micros: 100, currency: "EUR", missing_micros: 2_000_000 } };
    expect(missingOf(res)).toEqual(money(2_000_000, "EUR"));
    expect(plain(moneyErrorText(t, res))).toBe("Faltan 20,00 €");
    expect(missingOf({ ...res, code: "bags_not_active" })).toBeNull();
  });

  it("cada error de dinero tiene su frase, nunca el mensaje de la API", () => {
    const fail = (code: string | null, status = 409, info?: Record<string, unknown>) => ({ ok: false as const, status, message: "raw backend detail", code, info });
    expect(plain(moneyErrorText(t, fail("bag_below_spent", 409, { available_micros: 1_234_567 }), "USD"))).toBe("Solo puedes devolver hasta 12,34 USD, lo que le queda.");
    expect(moneyErrorText(t, fail("bags_not_active"))).toBe("Antes de asignar, confirma el reparto de tu saldo en bolsas.");
    expect(moneyErrorText(t, fail("currency_mismatch", 422))).toMatch(/moneda de su bolsa ha cambiado/);
    expect(moneyErrorText(t, fail("request_already_sent_today", 429))).toBe("Ya se pidió hoy para este cliente.");
    expect(moneyErrorText(t, fail(null, 403))).toBe(t("common.forbidden"));
    expect(moneyErrorText(t, fail(null, 500))).toBe("No se pudo hacer. Inténtalo de nuevo.");
  });
});

describe("«Pedir saldo» (45.7)", () => {
  const now = Date.parse("2026-10-28T12:00:00Z");
  it("después de pedir, «Pedido hace…»", () => {
    expect(requestedText(t, now - 10_000, now)).toBe("Pedido hace un momento");
    expect(requestedText(t, now - 5 * 60_000, now)).toBe("Pedido hace 5 minutos");
    expect(requestedText(t, now - 3 * 3_600_000, now)).toBe("Pedido hace 3 horas");
    expect(requestedText(t, null, now)).toBe("Pedido hoy");
  });

  it("la nota, hasta 280 caracteres", () => {
    expect(noteProblem("a".repeat(280))).toBeNull();
    expect(noteProblem("a".repeat(281))).toBe("too_long");
  });
});

describe("«Gasto por día» y su tabla (46.3)", () => {
  const daily: UsageDaily = {
    currency: "EUR",
    days: ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"],
    lines: ["conversations", "meta", "build", "companion"],
    series: {
      conversations: [100_000, 0, 250_000, 0, 0, 50_000, 1_000],
      meta: [10_000, 10_000, 0, 0, 0, 0, 0],
      build: [0, 0, 0, 0, 0, 0, 500_000],
      companion: [0, 20_000, 0, 0, 0, 0, 0],
    },
    total: [110_000, 30_000, 250_000, 0, 0, 50_000, 501_000],
    approx_lines: ["meta"],
  };

  it("sin filtro, lo que paga el partner; con filtro, la partida elegida", () => {
    expect(chartLines(daily, null)).toEqual(["conversations", "companion"]);
    expect(chartLines(daily, "meta")).toEqual(["meta"]);
    expect(chartLines({ lines: ["build"] }, null)).toEqual([]);
  });

  it("una columna por día, con el día de la semana en 7 días y «Hoy» al final", () => {
    const cols = chartColumns(t, daily, ["conversations", "companion"]);
    expect(cols).toHaveLength(7);
    expect(cols[0]).toMatchObject({ key: "2026-10-22", label: "jue", values: [100_000, 0] });
    expect(cols[0]!.title).toBe("Jueves, 22 oct");
    expect(cols[6]!.label).toBe("Hoy");
    const month = chartColumns(t, { ...daily, days: Array.from({ length: 30 }, (_, i) => `2026-09-${String(i + 1).padStart(2, "0")}`) }, ["build"]);
    expect(month[0]!.label).toBe("1");
    expect(month[0]!.values).toEqual([0]);
  });

  it("la tabla equivalente suma cada día y el periodo cuadra con las series", () => {
    const rows = chartTable(t, daily, ["conversations", "companion"]);
    expect(rows.map((r) => r.total)).toEqual([100_000, 20_000, 250_000, 0, 0, 50_000, 1_000]);
    expect(rows[1]).toMatchObject({ day: "2026-10-23", values: [0, 20_000] });
    expect(chartTotal(daily, ["conversations", "companion"])).toBe(421_000);
    expect(chartTotal(daily, ["conversations", "meta", "build", "companion"])).toBe(daily.total.reduce((a, b) => a + b, 0));
  });

  it("los filtros de la URL", () => {
    expect(parseDays("7")).toBe(7);
    expect(parseDays("90")).toBe(90);
    expect(parseDays("12")).toBe(30);
    expect(parseDays(undefined)).toBe(30);
    expect(parseLine("build")).toBe("build");
    expect(parseLine("tokens")).toBeNull();
  });
});

describe("lo demás", () => {
  it("«Construcción y pruebas»: la parte del tope gastada", () => {
    expect(buildShare(EUR(40), EUR(50))).toBeCloseTo(0.8);
    expect(buildShare(EUR(60), EUR(50))).toBe(1);
    expect(buildShare(EUR(1), null)).toBeNull();
  });

  it("los días al ritmo de 7 días", () => {
    expect(daysText(t, 4.4)).toBe("Unos 4 días");
    expect(daysText(t, 1)).toBe("Un día");
    expect(daysText(t, null)).toBe("Sin ritmo para estimarlo");
  });

  it("«Repartir tu saldo en bolsas» está pendiente solo con topes y sin confirmar (55.3)", () => {
    const proposal = { confirmed_at: null, clients: [{ ref: "a", amount: USD(10) }, { ref: "b", amount: USD(2.5) }] };
    expect(migrationPending(proposal)).toBe(true);
    expect(migrationPending({ ...proposal, confirmed_at: "2026-10-27T10:00:00Z" })).toBe(false);
    expect(migrationPending({ confirmed_at: null, clients: [] })).toBe(false);
    expect(migrationPending(null)).toBe(false);
    expect(proposalTotals(proposal)).toEqual([USD(12.5)]);
  });
});

describe("el aviso de «Pedir saldo» (45.7)", () => {
  it("dice para quién y, si la trae, la nota", async () => {
    const { notificationText } = await import("@/components/notifications/render");
    const base = { kind: "client.balance_request", external_client_ref: "flor-y-encanto", data: { external_client_ref: "flor-y-encanto", by: "x", note: "" } };
    expect(notificationText("es", base, { "flor-y-encanto": "Flor y Encanto" })).toBe("Te piden saldo para Flor y Encanto.");
    expect(notificationText("es", { ...base, data: { ...base.data, note: " Se acaba el viernes " } }, { "flor-y-encanto": "Flor y Encanto" })).toBe(
      "Te piden saldo para Flor y Encanto: «Se acaba el viernes»",
    );
  });
});

describe("el reparto ajustable (55.3)", () => {
  const proposal = { confirmed_at: null, clients: [{ ref: "a", amount: money(1_234_567, "USD") }, { ref: "b", amount: USD(7) }] };

  it("solo manda lo que cambió, en cien milésimas, y suma lo que quedará", () => {
    const same = migrationAdjust(proposal, { a: "12,34", b: "7,00" });
    expect(same.adjust).toEqual({});
    expect(same.total).toBe(1_234_567 + 700_000);
    const changed = migrationAdjust(proposal, { a: "20", b: "7,00" });
    expect(changed.adjust).toEqual({ a: 2_000_000 });
    expect(changed.total).toBe(2_000_000 + 700_000);
    expect(migrationAdjust(proposal, { a: "0", b: "7" }).adjust).toEqual({ a: 0 });
  });

  it("lo que no se lee como importe no se manda", () => {
    expect(migrationAdjust(proposal, { a: "doce", b: "" }).invalid).toEqual(["a", "b"]);
  });
});

describe("las secciones a las que llegan los avisos (?tab=)", () => {
  it("cada pestaña es una sección de la pantalla del agente", async () => {
    const { sectionForTab } = await import("@/components/builder/builder-model");
    expect(sectionForTab("advanced")).toBe("agente-avanzado");
    expect(sectionForTab("quality")).toBe("agente-calidad");
    expect(sectionForTab("integrations")).toBe("agente-conectores");
    expect(sectionForTab("tests")).toBe("agente-pruebas");
    expect(sectionForTab("performance")).toBe("agente-rendimiento");
    expect(sectionForTab("improvements")).toBe("agente-mejoras");
    expect(sectionForTab("nope")).toBeNull();
    expect(sectionForTab(undefined)).toBeNull();
  });
});

describe("el aviso dice quién pide saldo (45.7)", () => {
  it("con `by_name`, con y sin nota", async () => {
    const { notificationText } = await import("@/components/notifications/render");
    const n = { kind: "client.balance_request", external_client_ref: "lola", data: { by_name: "Lucía Pérez", note: "" } };
    expect(notificationText("es", n, { lola: "Lola" })).toBe("Lucía Pérez pide saldo para Lola.");
    expect(notificationText("es", { ...n, data: { by_name: "Lucía Pérez", note: "Urge" } }, { lola: "Lola" })).toBe("Lucía Pérez pide saldo para Lola: «Urge»");
  });
});
