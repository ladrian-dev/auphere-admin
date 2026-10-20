import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Spend, UsageSummary } from "@/api/endpoints";
import { UsageView } from "@/features/usage/usage-view";
import { t as translate, type Locale, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T064, R4.2, R4.4, R4.5): Consumo is read-only — the balance, the
 * month and its projection, per day and per agent; never a way to buy.
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

async function view(locale: Locale = "es", s: UsageSummary | null = summary()) {
  const t = (k: MessageKey, v?: Record<string, string | number>) => translate(locale, k, v);
  const onDays = jest.fn();
  await render(
    <UsageView
      summary={s}
      spend={spend}
      spendFailed={false}
      days={30}
      onDays={onDays}
      agents={[]}
      agent={null}
      onAgent={jest.fn()}
      t={t}
      locale={locale}
      now={new Date("2026-10-08T12:00:00Z")}
      onRetry={jest.fn()}
      onWeb={jest.fn()}
    />,
  );
  return { onDays };
}

it("the balance, how long it lasts, the month and its projection", async () => {
  await view();
  expect(screen.getByText(/30,13/)).toBeTruthy();
  expect(screen.getByText("Cubre unos 11 días al ritmo de esta semana")).toBeTruthy();
  expect(screen.getByText(/A este ritmo, .*41,00.* a fin de mes/)).toBeTruthy();
});

it("spend per day with 7, 30 and 90", async () => {
  const { onDays } = await view();
  // The group is a radiogroup for screen readers; each period is a radio.
  expect(screen.getAllByRole("radio")).toHaveLength(3);
  expect(screen.getByRole("radio", { name: "30 días" }).props.accessibilityState).toEqual({ checked: true });
  await fireEvent.press(screen.getByRole("radio", { name: "90 días" }));
  expect(onDays).toHaveBeenCalledWith(90);
  expect(screen.getByLabelText(/Gasto por día en dólares/)).toBeTruthy();
});

it("the split by agent", async () => {
  await view();
  expect(screen.getByRole("header", { name: "Gasto por agente" })).toBeTruthy();
  expect(screen.getByLabelText(/Recepción: .*62 %/)).toBeTruthy();
});

it.each<Locale>(["es", "en"])("no buy, top-up or «ask for balance» anywhere (%s)", async (locale) => {
  await view(locale);
  for (const word of [/comprar/i, /recargar/i, /pedir saldo/i, /\bbuy\b/i, /top[- ]?up/i, /ask .* for more balance/i]) {
    expect(screen.queryByText(word)).toBeNull();
    expect(screen.queryByRole("button", { name: word })).toBeNull();
  }
});

it("no technical detail and no export: those stay on the web", async () => {
  await view();
  // Only the pointer to the web mentions it; nothing here exports.
  expect(screen.queryByRole("button", { name: /^(exportar|export)/i })).toBeNull();
  expect(screen.queryByText(/medidor|meter/i)).toBeNull();
  expect(screen.getByRole("button", { name: "El detalle técnico y la exportación están en la consola web." })).toBeTruthy();
});

it("a failed read is an error with retry, never zeros", async () => {
  await view("es", null);
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.queryByText(/30,13/)).toBeNull();
});
