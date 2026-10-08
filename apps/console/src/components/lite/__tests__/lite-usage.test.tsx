import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { LiteSpend, LiteUsageDetail, LiteUsageSummary } from "@/lib/backend/lite";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  usePathname: () => "/usage",
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

const { LiteUsageView } = await import("../lite-usage-view");

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const NOW = new Date("2026-10-08T12:00:00Z");

const summary = (o: Partial<LiteUsageSummary> = {}): LiteUsageSummary => ({
  balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11 },
  month: { spent_cents: 1626, projection_cents: 8401, conversations: 70, avg_per_conversation_cents: 23 },
  by_agent: null,
  errors: [],
  ...o,
});
const spend: LiteSpend = {
  currency: "USD",
  days: ["2026-10-06", "2026-10-07", "2026-10-08"],
  series_cents: [240, 360, 166],
  month_cents: 1626,
  projected_cents: 8401,
};
const detail: LiteUsageDetail = {
  since: "2026-09-08T00:00:00Z",
  until: "2026-10-08T00:00:00Z",
  buckets: [{ meter: "channel.message", source: "channel", quantity: 1284, billable_qty: 1284, records: 1284 }],
  totals_by_meter: { "channel.message": 1284 },
  total_records: 1284,
};

function view(props: Partial<Parameters<typeof LiteUsageView>[0]> = {}) {
  return render(
    <LocaleProvider locale="es">
      <LiteUsageView clientName="Flor y Encanto" summary={summary()} spend={spend} detail={detail} days={30} t={t} locale="es" now={NOW} {...props} />
    </LocaleProvider>,
  );
}

/** Spec 030 (R5): the Consumo of one client, read-only. */
describe("LiteUsageView", () => {
  it("shows balance, month spend with projection and conversations with their average", () => {
    view();
    expect(screen.getByText("Saldo disponible")).toBeTruthy();
    expect(screen.getByText(/A este ritmo, 84,01/)).toBeTruthy();
    expect(screen.getByText("Conversaciones del mes")).toBeTruthy();
    expect(screen.getByText(/0,23 .* de media cada una/)).toBeTruthy();
  });

  it("offers nothing to buy, move or configure", () => {
    view();
    expect(screen.queryByText(/Comprar/)).toBeNull();
    expect(screen.queryByText(/Alertas de consumo/)).toBeNull();
    expect(screen.queryByText(/Cambiar tope/)).toBeNull();
    // Without other clients there is nothing to choose in the spend chart.
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("does not project an empty month", () => {
    view({ summary: summary({ month: { spent_cents: 0, projection_cents: null, conversations: 0, avg_per_conversation_cents: null } }) });
    expect(screen.getByText("Sin gasto este mes")).toBeTruthy();
    expect(screen.queryByText(/A este ritmo/)).toBeNull();
  });

  it("links the CSV through the client route", () => {
    view();
    const link = screen.getByRole("link", { name: /Exportar CSV/ });
    expect(link.getAttribute("href")).toBe("/api/lite/usage/export?days=30&lang=es");
  });

  it("says when a part could not be read, and when everything failed", () => {
    const { unmount } = view({ summary: summary({ errors: ["month"], month: null }) });
    expect(screen.getByText(/Una parte del Consumo no se pudo cargar/)).toBeTruthy();
    unmount();
    view({ summary: null, spend: null, detail: null });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getAllByText("No se pudo leer ahora").length).toBeGreaterThan(0);
  });

  it("shows a spend-per-agent table only with more than one agent", () => {
    view({
      summary: summary({
        by_agent: [
          { agent_id: "a1", name: "Agente de ventas", conversations: 41, spent_cents: 950, share_pct: 58 },
          { agent_id: "a2", name: "Agente de soporte", conversations: 29, spent_cents: 676, share_pct: 42 },
        ],
      }),
    });
    expect(screen.getByRole("heading", { name: "Gasto por agente" })).toBeTruthy();
    expect(screen.getByText("Agente de soporte")).toBeTruthy();
  });

  it("narrows the spend chart to one agent only with more than one (spec 030, iteration 3)", async () => {
    const agents = [
      { id: "a1", name: "Agente principal" },
      { id: "a2", name: "Ventas" },
    ];
    const { unmount } = view({ agents: agents.slice(0, 1) });
    expect(screen.queryByRole("combobox", { name: "Agente" })).toBeNull();
    unmount();

    view({ agents, agent: "a2" });
    const select = screen.getByRole("combobox", { name: "Agente" });
    expect(select).toHaveValue("a2");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos los agentes", "Agente principal", "Ventas"]);
    await userEvent.selectOptions(select, "");
    expect(push).toHaveBeenLastCalledWith("/usage?#gasto", { scroll: false });
    await userEvent.selectOptions(select, "a1");
    expect(push).toHaveBeenLastCalledWith("/usage?agent=a1#gasto", { scroll: false });
  });
});
