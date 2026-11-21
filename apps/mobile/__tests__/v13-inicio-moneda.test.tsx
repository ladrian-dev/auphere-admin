import { render, screen } from "@testing-library/react-native";

import type { Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 069, R21.1 (T021): every amount in the currency of its bag. Before the
 * fix, Inicio wrote «Gasto del mes» without one, and `formatMoney` fell back to
 * US$ (`home-view.tsx`, `formatMoney(spend.total_cents, locale)`). Layout
 * agnostic on purpose: it only asks which currency is on screen.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

const eur = {
  spend_month: { total_cents: 1626, currency: "EUR", by_agent: null },
  conversations: { last_7d: 12, prev_7d: null, daily: [] },
  waiting: { count: 0, first_conversation_id: null },
  balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11, month_days_left: 24, currency: "EUR" },
  attention: [],
  errors: [],
} as unknown as Home;

const me = {
  client: { name: "Flor y Encanto", modules: ["panel", "inbox", "usage"] },
  nav: ["panel", "inbox", "usage"],
  balance_contact: { kind: "partner", name: "Amacrux" },
  agents: [{ id: "a1", name: "Recepción" }],
  channels: [],
} as unknown as Me;

it("a bag in EUR: the month's spend says € and nothing on Inicio says US$", async () => {
  await render(
    <HomeView me={me} home={eur} t={t} locale="es" now={new Date("2026-10-08T12:00:00Z")} onRetry={jest.fn()} onAttend={jest.fn()} onUsage={jest.fn()} />,
  );
  expect(screen.getAllByText(/16,26\s*€/).length).toBeGreaterThan(0);
  expect(screen.queryAllByText(/US\$/)).toHaveLength(0);
});

it("a bag in CLP: no decimals, in pesos", async () => {
  const clp = { ...eur, spend_month: { total_cents: 1250000, currency: "CLP", by_agent: null }, balance: { ...eur.balance!, currency: "CLP" } } as Home;
  await render(
    <HomeView me={me} home={clp} t={t} locale="es" now={new Date("2026-10-08T12:00:00Z")} onRetry={jest.fn()} onAttend={jest.fn()} onUsage={jest.fn()} />,
  );
  expect(screen.getAllByText(/12\.500\s*CLP|\$\s*12\.500|12\.500\s*\$/).length).toBeGreaterThan(0);
  expect(screen.queryAllByText(/US\$/)).toHaveLength(0);
});
