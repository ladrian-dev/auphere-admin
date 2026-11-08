import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type MessageKey, t as translate } from "@/i18n/messages";
import type { LiteHome } from "@/lib/backend/lite";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const { LiteSpendCard } = await import("../lite-spend-card");

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
type Spend = NonNullable<LiteHome["spend_month"]>;

const split: Spend["by_agent"] = [
  { agent_id: "a1", name: "Citas", cents: 950 },
  { agent_id: "a2", name: "Ventas", cents: 676 },
];

function card(spend: Spend) {
  const { container } = render(<LiteSpendCard spend={spend} showUsageLink={false} t={t} locale="es" />);
  return container.querySelector('[data-slot="lite-spend"]') as HTMLElement;
}

/**
 * Bug `gasto-del-mes-a-cero-con-bolsas`: with bags the spend is the bag's, in
 * the bag's currency (EUR in the euro zone). The card used to print US$ always.
 */
describe("LiteSpendCard currency", () => {
  it("formats the total and every agent in the bag's currency", () => {
    const el = card({ total_cents: 1626, by_agent: split, currency: "EUR" });
    expect(within(el).getByText(/^16,26\s€$/, { selector: ".sr-only" })).toBeTruthy();
    expect(within(el).getByText(/^9,50\s€$/)).toBeTruthy();
    expect(within(el).getByText(/^6,76\s€$/)).toBeTruthy();
    expect(el.textContent).not.toContain("US$");
  });

  it("stays in US$ when the spend comes without a currency (no bags)", () => {
    const el = card({ total_cents: 1626, by_agent: null });
    expect(within(el).getByText(/^16,26\sUS\$$/, { selector: ".sr-only" })).toBeTruthy();
    expect(screen.queryByText(/€/)).toBeNull();
  });
});
