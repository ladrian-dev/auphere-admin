import { act, render, screen } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import type { Spend, UsageSummary } from "@/api/endpoints";
import { weekly } from "@/features/charts/day-bars";
import { UsageView, type Period } from "@/features/usage/usage-view";
import { t as translate, type Locale, type MessageKey } from "@/i18n/t";

/**
 * Spec 069, Historia 6, Requisito 18 (T039): Consumo says how long the balance
 * lasts, the month, the bars of 7, 30 and 90 days, and whom to ask for more
 * — as text, with nothing to press. The figures run to their value (micro 4)
 * and a screen reader hears only the final one.
 */
const summary = (o: Partial<UsageSummary> = {}): UsageSummary =>
  ({
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11, month_days_left: 24, currency: "USD" },
    month: { spent_cents: 1626, projection_cents: 4100, conversations: 75, avg_per_conversation_cents: 22, currency: "USD" },
    by_agent: null,
    errors: [],
    partner_name: "Amacrux",
    ...o,
  }) as UsageSummary;

function series(n: number, cents: (i: number) => number, currency = "USD"): Spend {
  const days = Array.from({ length: n }, (_, i) => new Date(Date.UTC(2026, 9, 8) - (n - 1 - i) * 86_400_000).toISOString().slice(0, 10));
  return { currency, days, series_cents: days.map((_, i) => cents(i)), month_cents: 1626, projected_cents: 4100 } as Spend;
}

type P = { locale?: Locale; summary?: UsageSummary; spend?: Spend | null; days?: Period; anySpend?: boolean | null };

function element(p: P) {
  const locale = p.locale ?? "es";
  const t = (k: MessageKey, v?: Record<string, string | number>) => translate(locale, k, v);
  return (
    <UsageView
      summary={p.summary ?? summary()}
      spend={p.spend === undefined ? series(30, (i) => (i % 3 === 0 ? 100 : 0)) : p.spend}
      spendFailed={false}
      anySpend={p.anySpend === undefined ? true : p.anySpend}
      days={p.days ?? 30}
      onDays={jest.fn()}
      agents={[]}
      agent={null}
      onAgent={jest.fn()}
      t={t}
      locale={locale}
      now={new Date("2026-10-08T12:00:00Z")}
      onRetry={jest.fn()}
      onWeb={jest.fn()}
      contact={{ kind: "partner", name: "Amacrux" }}
    />
  );
}

describe("how long the balance lasts (R18.1)", () => {
  it.each([
    [11, "Para unos 11 días, al ritmo de los últimos 7 días."],
    [125, "Para unos 4 meses, al ritmo de los últimos 7 días."],
    [1.2, "Para 1 día, al ritmo de los últimos 7 días."],
    [0.5, "Para menos de un día, al ritmo de los últimos 7 días."],
  ])("%s days left: «%s»", async (days, line) => {
    await render(element({ summary: summary({ balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: days, month_days_left: 24, currency: "USD" } }) }));
    expect(screen.getByText(line)).toBeTruthy();
  });

  it("the date it runs out and the month it covers stay (spec 044, R13.1; 042)", async () => {
    await render(element({}));
    expect(screen.getByText("Te alcanza hasta el lunes 19")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Días del mes que cubre el saldo" })).toBeTruthy();
  });

  it("a bag in EUR: every figure in €, none in US$ (Historia 6, escenario 1; R21.1)", async () => {
    const eur = summary({
      balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11, month_days_left: 24, currency: "EUR" },
      month: { spent_cents: 1626, projection_cents: 4100, conversations: 75, avg_per_conversation_cents: 22, currency: "EUR" },
    });
    await render(element({ summary: eur, spend: series(30, () => 10, "EUR") }));
    expect(screen.getAllByText(/€/).length).toBeGreaterThan(2);
    expect(screen.queryAllByText(/US\$/)).toHaveLength(0);
  });
});

describe("whom to ask, as text (R18.2)", () => {
  it.each<Locale>(["es", "en"])("«Pídeselo a {partner}» and nothing to press or follow (%s)", async (locale) => {
    await render(element({ locale }));
    expect(screen.getByText(locale === "es" ? "¿Necesitas más saldo? Pídeselo a Amacrux." : "Need more balance? Ask Amacrux.")).toBeTruthy();
    for (const word of [/recargar/i, /comprar/i, /top[- ]?up/i, /\bbuy\b/i]) {
      expect(screen.queryAllByText(word)).toHaveLength(0);
      expect(screen.queryByRole("button", { name: word })).toBeNull();
      expect(screen.queryByRole("link", { name: word })).toBeNull();
    }
    expect(screen.queryByRole("button", { name: /Amacrux/ })).toBeNull();
  });
});

describe("the bars (R18.1)", () => {
  it("7 and 30 days: one bar per day, three dates on the axis and «Por día»", async () => {
    await render(element({}));
    expect(screen.getByText("Por día")).toBeTruthy();
    const chart = screen.getByRole("image");
    expect(chart.props.accessibilityLabel).toMatch(/^Gasto por día: /);
    expect((chart.props.accessibilityLabel as string).split(", ")).toHaveLength(30);
    expect(screen.getByTestId("chart-axis").children).toHaveLength(3);
  });

  it("90 days: 13 weekly bars counted back from today, and «Por semana»", async () => {
    await render(element({ days: 90, spend: series(90, () => 100) }));
    expect(screen.getByText("Por semana")).toBeTruthy();
    const label = screen.getByRole("image").props.accessibilityLabel as string;
    expect(label).toMatch(/^Gasto por semana: /);
    expect(label.split(", ")).toHaveLength(13);
    // The last week ends today and holds 7 days; the first holds what is left (6).
    expect(label).toMatch(/7,00\s*US\$$/);
    expect(label).toMatch(/^Gasto por semana: [^:]+ – [^:]+: 6,00\s*US\$/);
  });

  it("while 90 days load, the 30 on screen keep their own shape (placeholder data)", async () => {
    await render(element({ days: 90, spend: series(30, () => 100) }));
    expect(screen.getByText("Por día")).toBeTruthy();
    expect((screen.getByRole("image").props.accessibilityLabel as string).split(", ")).toHaveLength(30);
  });

  it("weekly() groups by 7 from the end", () => {
    const w = weekly(Array.from({ length: 90 }, (_, i) => `d${i}`), Array.from({ length: 90 }, () => 1));
    expect(w).toHaveLength(13);
    expect(w[0]).toEqual({ from: "d0", to: "d5", cents: 6 });
    expect(w[12]).toEqual({ from: "d83", to: "d89", cents: 7 });
  });
});

describe("micro 4: the figure runs to its value (R18.3)", () => {
  afterEach(() => {
    jest.useRealTimers();
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(false);
  });

  it("Historia 6, escenario 2: from 30 to 90 days the total runs, and the screen reader hears only the final value", async () => {
    jest.useFakeTimers();
    const r = await render(element({ days: 30, spend: series(30, () => 10) }));
    expect(screen.getByTestId("usage-period-total").props.accessibilityLabel).toMatch(/^3,00\s*US\$$/);
    await r.rerender(element({ days: 90, spend: series(90, () => 10) }));
    // The label is the end at once; the drawn figure is still on its way.
    expect(screen.getByRole("header", { name: "Gasto de los últimos 90 días" })).toBeTruthy();
    expect(screen.getByTestId("usage-period-total").props.accessibilityLabel).toMatch(/^9,00\s*US\$$/);
    expect(screen.queryByText(/^9,00\s*US\$$/)).toBeNull();
    await act(async () => jest.advanceTimersByTime(300));
    expect(screen.getByText(/^9,00\s*US\$$/)).toBeTruthy();
  });

  it("with «Reducir movimiento» the final value at once", async () => {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
    const r = await render(element({ days: 30, spend: series(30, () => 10) }));
    await act(async () => undefined);
    await r.rerender(element({ days: 90, spend: series(90, () => 10) }));
    expect(screen.getByText(/^9,00\s*US\$$/)).toBeTruthy();
  });

  it("the balance runs too, its label always the final value", async () => {
    await render(element({}));
    expect(screen.getByLabelText(/^Saldo disponible: 30,13\s*US\$/)).toBeTruthy();
  });
});
