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

type Contact = { kind: "auphere" | "partner"; name: string } | null;

async function view(
  p: { locale?: Locale; summary?: UsageSummary | null; anySpend?: boolean | null; spend?: Spend | null; contact?: Contact } = {},
) {
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
      contact={p.contact === undefined ? { kind: "auphere", name: "Auphere" } : p.contact}
    />,
  );
  return { onDays, onWeb };
}

it("the balance, how long it lasts, the month and its projection — the same cents as before (R10.1)", async () => {
  await view();
  expect(screen.getByLabelText(/^Saldo disponible: .*30,13/)).toBeTruthy();
  // Spec 044, R13.1: «how long it lasts» is now the answer first (below), not a «Cubre unos N días» row.
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
  // Spec 044, R13.1 and R13.4: one sentence says whom to talk to for more balance; nothing offers it.
  const whom = locale === "es" ? "Para recargar, habla con quien gestiona tu negocio en Auphere." : "To top up, talk to whoever manages your business at Auphere.";
  for (const word of [/comprar/i, /recargar/i, /pedir saldo/i, /\bbuy\b/i, /top[- ]?up/i, /ask .* for more balance/i]) {
    expect(screen.queryAllByText(word).filter((el) => el.props.children !== whom)).toHaveLength(0);
    expect(screen.queryByRole("button", { name: word })).toBeNull();
    expect(screen.queryByRole("link", { name: word })).toBeNull();
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

/**
 * Spec 044, Historia 8, Requisito 13: Consumo starts with the answer to «how
 * long does it last?», says whom to talk to, and never makes up a date.
 */
describe("the answer first (R13)", () => {
  it("«Te alcanza hasta el <día> <n>» at the 7-day pace, and whom to talk to", async () => {
    await view();
    // 8 October plus 11 whole days: Monday 19.
    expect(screen.getByText("Te alcanza hasta el lunes 19")).toBeTruthy();
    expect(screen.getByText("Al ritmo de los últimos 7 días.")).toBeTruthy();
    expect(screen.getByText("Para recargar, habla con quien gestiona tu negocio en Auphere.")).toBeTruthy();
  });

  it("says the month when it is not this one", async () => {
    await view({ summary: summary({ balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 26.4 } }) });
    expect(screen.getByText("Te alcanza hasta el martes 3 de noviembre")).toBeTruthy();
  });

  it("takes the API's own date when it gives one", async () => {
    const balance = { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11, runs_out_on: "2026-10-17" };
    await view({ summary: summary({ balance } as Partial<UsageSummary>) });
    expect(screen.getByText("Te alcanza hasta el sábado 17")).toBeTruthy();
  });

  it("with a partner, names it", async () => {
    await view({ contact: { kind: "partner", name: "Amacrux Demo" } });
    expect(screen.getByText("Para recargar, habla con Amacrux Demo.")).toBeTruthy();
  });

  it.each([
    ["no spend in 7 days", { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: null }, "Sin gasto en los últimos 7 días"],
    ["no balance assigned", { assigned: false, remaining_cents: null, cap_cents: null, days_left: null }, "Todavía no tienes un tope asignado"],
    ["used up", { assigned: true, remaining_cents: 0, cap_cents: 5000, days_left: 0 }, "Saldo agotado: el agente no responde"],
  ])("%s: says it, and no date", async (_name, balance, line) => {
    await view({ summary: summary({ balance } as Partial<UsageSummary>) });
    expect(screen.getByText(line)).toBeTruthy();
    expect(screen.queryByText(/Te alcanza hasta/)).toBeNull();
  });

  it("the chart says its period and its total (R13.3)", async () => {
    await view();
    expect(screen.getByRole("header", { name: "Gasto de los últimos 30 días" })).toBeTruthy();
    expect(screen.getByText(/3,50/)).toBeTruthy();
  });
});
