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
  balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11.4, month_days_left: 24, runs_out_on: "2026-10-19" },
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

  it("names each day of the spend chart as an image: a bare div cannot carry a name (axe aria-prohibited-attr, T105)", () => {
    view();
    const bars = screen.getAllByRole("img", { name: /: / });
    expect(bars).toHaveLength(spend.days.length);
    expect(bars[0]?.getAttribute("aria-label")).toMatch(/2,40/);
    for (const bar of bars) expect(bar.tabIndex).toBe(0);
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
  // ── Spec 045 (R4, R6.3): the balance first, the detail in three families ──
  it("opens with the balance, big, and how far it goes", () => {
    const { container } = view();
    const cards = screen.getByRole("region", { name: "Saldo y gasto" });
    const first = cards.firstElementChild as HTMLElement;
    expect(first.getAttribute("data-slot")).toBe("lite-balance");
    expect(within(first).getByRole("heading", { name: "Saldo disponible" })).toBeTruthy();
    expect(within(first).getByText("30,13 US$", { selector: ".sr-only" })).toBeTruthy();
    expect(within(first).getByText("Te alcanza hasta el lunes 19")).toBeTruthy();
    expect(container.querySelector('[data-slot="lite-balance"] progress')?.getAttribute("aria-valuetext")).toBe("Cubre 11 de 24 días del mes");
    expect(container.querySelector('[data-slot="lite-balance"] [data-slot="meter"]')?.getAttribute("data-tone")).toBe("warning");
  });

  it("names the month when the balance lasts into the next one", () => {
    view({ summary: summary({ balance: { ...summary().balance!, days_left: 40, runs_out_on: "2026-11-17" } }) });
    expect(screen.getByText("Te alcanza hasta el martes, 17 de noviembre")).toBeTruthy();
  });

  it("without spend there is no date to promise", () => {
    view({ summary: summary({ balance: { ...summary().balance!, days_left: null, runs_out_on: null } }) });
    expect(screen.queryByText(/Te alcanza hasta/)).toBeNull();
    expect(screen.getByText("Sin gasto en los últimos 7 días")).toBeTruthy();
  });

  it("a used-up balance says the agent stopped, never «it lasts until today»", () => {
    const { container } = view({
      summary: summary({ balance: { ...summary().balance!, remaining_cents: 0, days_left: 0, runs_out_on: "2026-10-08" } }),
    });
    expect(screen.queryByText(/Te alcanza hasta/)).toBeNull();
    expect(screen.getByText("Saldo agotado: el agente no responde")).toBeTruthy();
    expect(container.querySelector('[data-slot="lite-balance"] [data-slot="meter"]')?.getAttribute("data-tone")).toBe("danger");
  });

  it("without an allocation it says so instead of an invented zero", () => {
    view({ summary: summary({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null, month_days_left: 24, runs_out_on: null } }) });
    expect(screen.getByText("Todavía no tienes un tope asignado")).toBeTruthy();
    expect(screen.queryByText(/Te alcanza hasta/)).toBeNull();
  });

  it("the technical detail is one WhatsApp row in three families, with the period's spend", () => {
    view({
      detail: {
        ...detail,
        totals_by_meter: { "channel.message": 1284, "llm.input_tokens": 120000, "llm.output_tokens": 30000, "media.image": 9, "media.document": 3 },
      },
    });
    const table = screen.getByRole("table", { name: "Detalle técnico: mensajes, uso del modelo y multimedia" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Canal", "Mensajes", "Uso del modelotokens", "Multimediaarchivos", "Gasto del periodo"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    const cells = within(rows[0]!).getAllByRole("cell").map((c) => c.textContent?.replace(/\s/g, " "));
    expect(within(rows[0]!).getByRole("rowheader").textContent).toBe("WhatsApp");
    // 2,40 + 3,60 + 1,66 US$ of the period's spend.
    expect(cells).toEqual(["1284", "150.000", "12", "7,66 US$"]);
    expect(screen.queryByRole("columnheader", { name: /Otros/ })).toBeNull();
    expect(document.body.textContent).not.toMatch(/Instagram|Messenger/);
  });

  it("an unknown meter gets an «Otros» column, only then", () => {
    view({ detail: { ...detail, totals_by_meter: { "channel.message": 10, "web.search": 4 } } });
    expect(screen.getByRole("columnheader", { name: /Otros/ })).toBeTruthy();
  });

  it("the period's spend is the client's whole spend, even with the chart narrowed to one agent", () => {
    const agents = [
      { id: "a1", name: "Agente principal" },
      { id: "a2", name: "Ventas" },
    ];
    view({ agents, agent: "a2", periodSpend: { ...spend, series_cents: [1000, 0, 26] } });
    const table = screen.getByRole("table", { name: "Detalle técnico: mensajes, uso del modelo y multimedia" });
    expect(within(table).getByText("10,26 US$")).toBeTruthy();
  });

  it("an unread spend leaves the money cell empty, never a zero", () => {
    view({ spend: null });
    const table = screen.getByRole("table", { name: "Detalle técnico: mensajes, uso del modelo y multimedia" });
    expect(within(table).getAllByRole("cell").at(-1)?.textContent).toBe("—");
  });

  it("an empty period says so", () => {
    view({ detail: { ...detail, buckets: [], totals_by_meter: {}, total_records: 0 } });
    expect(screen.getByText("Sin consumo en el periodo")).toBeTruthy();
    expect(screen.queryByRole("table", { name: /Detalle técnico/ })).toBeNull();
  });
});
