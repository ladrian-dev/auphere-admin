import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Spend, UsageSummary } from "@/api/endpoints";
import { UsageView } from "@/features/usage/usage-view";
import { t as translate, type Locale, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T064, R4.2, R4.4, R4.5): Consumo is read-only — the balance, the
 * month and its projection, per day and per agent; never a way to buy.
 * Spec 042 (T038, T039, R9, R6.2, R6.3, R10.1): no opening sentence, the
 * figures as rows of one group, the chart's period only when there is
 * something to chart, and one row that says it leaves for the web.
 */
const summary = (o: Partial<UsageSummary> = {}): UsageSummary =>
  ({
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11 },
    month: { spent_cents: 1626, projection_cents: 4100, conversations: 75, avg_per_conversation_cents: 22 },
    by_agent: [
      { agent_id: "a1", name: "Recepción", conversations: 50, spent_cents: 1000, share_pct: 62 },
      { agent_id: "a2", name: "Ventas", conversations: 25, spent_cents: 626, share_pct: 38 },
    ],
    errors: [],
    ...o,
  }) as UsageSummary;

const spend: Spend = {
  currency: "USD",
  days: ["2026-10-06", "2026-10-07", "2026-10-08"],
  series_cents: [100, 0, 250],
  month_cents: 1626,
  projected_cents: 4100,
} as Spend;

async function view(p: { locale?: Locale; summary?: UsageSummary | null; anySpend?: boolean | null; spend?: Spend | null } = {}) {
  const locale = p.locale ?? "es";
  const t = (k: MessageKey, v?: Record<string, string | number>) => translate(locale, k, v);
  const onDays = jest.fn();
  const onWeb = jest.fn();
  await render(
    <UsageView
      summary={p.summary === undefined ? summary() : p.summary}
      spend={p.spend === undefined ? spend : p.spend}
      spendFailed={false}
      anySpend={p.anySpend === undefined ? true : p.anySpend}
      days={30}
      onDays={onDays}
      agents={[]}
      agent={null}
      onAgent={jest.fn()}
      t={t}
      locale={locale}
      now={new Date("2026-10-08T12:00:00Z")}
      onRetry={jest.fn()}
      onWeb={onWeb}
    />,
  );
  return { onDays, onWeb };
}

it("the balance, how long it lasts, the month and its projection — the same cents as before (R10.1)", async () => {
  await view();
  expect(screen.getByLabelText(/^Saldo disponible: .*30,13/)).toBeTruthy();
  expect(screen.getByLabelText(/^Cubre unos 11 días al ritmo de esta semana/)).toBeTruthy();
  expect(screen.getByLabelText(/^Gasto del mes: .*16,26.*A este ritmo, .*41,00.* a fin de mes/)).toBeTruthy();
  expect(screen.getByLabelText(/^Conversaciones del mes: 75\. .*0,22.* de media cada una/)).toBeTruthy();
});

it("opens with the figures, not with a sentence that repeats the title (R9.1)", async () => {
  await view();
  expect(screen.queryByText("Tu saldo, lo que gastas y lo que se gasta cada día.")).toBeNull();
  expect(screen.queryByText(/Tu saldo, lo que gasta cada agente/)).toBeNull();
});

it("spend per day with 7, 30 and 90, and the period's total as the figure", async () => {
  const { onDays } = await view();
  // The group is a radiogroup for screen readers; each period is a radio.
  expect(screen.getAllByRole("radio")).toHaveLength(3);
  expect(screen.getByRole("radio", { name: "30 días" }).props.accessibilityState).toEqual({ checked: true });
  await fireEvent.press(screen.getByRole("radio", { name: "90 días" }));
  expect(onDays).toHaveBeenCalledWith(90);
  expect(screen.getByText(/3,50/)).toBeTruthy();
  expect(screen.getByLabelText(/Gasto por día en dólares/)).toBeTruthy();
});

it("with no spend in 90 days there is no period to choose, and it says what will fill the chart (R9.2)", async () => {
  await view({ anySpend: false, spend: null });
  expect(screen.queryAllByRole("radio")).toHaveLength(0);
  expect(screen.getByText("Cuando tus agentes atiendan conversaciones, aquí verás el gasto de cada día.")).toBeTruthy();
  expect(screen.queryByLabelText(/Gasto por día en dólares/)).toBeNull();
});

it("the split by agent", async () => {
  await view();
  expect(screen.getByRole("header", { name: "Gasto por agente" })).toBeTruthy();
  expect(screen.getByLabelText(/Recepción: .*62 %/)).toBeTruthy();
});

it.each<Locale>(["es", "en"])("no buy, top-up or «ask for balance» anywhere (%s)", async (locale) => {
  await view({ locale });
  for (const word of [/comprar/i, /recargar/i, /pedir saldo/i, /\bbuy\b/i, /top[- ]?up/i, /ask .* for more balance/i]) {
    expect(screen.queryByText(word)).toBeNull();
    expect(screen.queryByRole("button", { name: word })).toBeNull();
  }
});

it("the way to the web is one row that says it leaves the app and where it goes (R6.2, R6.3)", async () => {
  const { onWeb } = await view();
  expect(screen.queryByRole("button", { name: /^(exportar|export)/i })).toBeNull();
  expect(screen.queryByText(/medidor|meter/i)).toBeNull();
  expect(screen.getByTestId("row-indicator-external")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Abrir en la consola web. El detalle técnico y la exportación" }));
  expect(onWeb).toHaveBeenCalled();
});

it("a failed read is an error with retry, never zeros", async () => {
  await view({ summary: null });
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.queryByText(/30,13/)).toBeNull();
});
