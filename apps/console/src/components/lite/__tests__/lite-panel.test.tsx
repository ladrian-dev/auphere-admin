import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { LiteHome } from "@/lib/backend/lite";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const { LitePanelView } = await import("../lite-panel-view");

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const days = ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"];
const counts = [5, 21, 9, 7, 5, 12, 16];

function home(o: Partial<LiteHome> = {}): LiteHome {
  return {
    spend_month: { total_cents: 1626, by_agent: null },
    conversations: { last_7d: 75, prev_7d: null, daily: days.map((day, i) => ({ day, count: counts[i]! })) },
    waiting: { count: 3, first_conversation_id: "c-2" },
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11.4, month_days_left: 24, runs_out_on: "2026-10-19" },
    attention: [],
    errors: [],
    ...o,
  };
}

const who = (modules: string[] = ["panel", "inbox", "usage"]) => ({ name: "Valeria Ríos", clientName: "Flor y Encanto", modules });
const contact = { kind: "partner" as const, name: "Amacrux" };

function view(props: Partial<Parameters<typeof LitePanelView>[0]> = {}) {
  return render(
    <LocaleProvider locale="es">
      <LitePanelView who={who()} home={home()} contact={contact} t={t} locale="es" {...props} />
    </LocaleProvider>,
  );
}

/** Spec 030 (R4): the Panel of one client, in each of its states. */
describe("LitePanelView", () => {
  it("greets by first name under the business, with the client's figures", () => {
    view();
    expect(screen.getByRole("heading", { name: "Hola, Valeria" })).toBeTruthy();
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
    expect(screen.getByText(/16,26/, { selector: "span" })).toBeTruthy();
    expect(screen.getByText("Esperan a una persona")).toBeTruthy();
    expect(screen.getByText("Últimos 7 días · sin semana anterior para comparar")).toBeTruthy();
  });

  it("reads the month's spend as text: a paragraph cannot carry a name (axe aria-prohibited-attr, T105)", () => {
    view();
    const amount = screen.getByText(/16,26/, { selector: "span" });
    expect(amount.closest("p")?.hasAttribute("aria-label")).toBe(false);
    expect(amount.getAttribute("aria-hidden")).toBeNull();
  });

  it("has no waiting card and no inbox line without the inbox", () => {
    view({ who: who(["panel"]), home: home({ waiting: null }) });
    expect(screen.queryByText("Esperan a una persona")).toBeNull();
    expect(screen.getByText("Todo en orden. El saldo alcanza para el mes.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ver consumo" })).toBeNull();
  });

  it("says whom to ask when the balance will not last, without a buy button", () => {
    view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }] }) });
    expect(screen.getByText("Te quedarás sin saldo en unos 4 días. Pide más saldo a Amacrux.")).toBeTruthy();
    expect(screen.queryByText(/Comprar/)).toBeNull();
  });

  it("points «Atender ahora» and the waiting card at the Inbox filtered to what waits, the first one open", () => {
    view({ home: home({ attention: [{ kind: "waiting", count: 3, days_left: null }] }) });
    // `Button` con `render={<Link />}` es un enlace con rol de botón (base-ui).
    // Spec 042: «Atender ahora»; spec 045: a la Bandeja filtrada por lo que espera.
    const attend = screen.getByRole("button", { name: "Atender ahora" });
    expect(attend.getAttribute("href")).toBe("/inbox?filter=waiting&c=c-2");
    const card = screen.getByText("Esperan a una persona").closest("a");
    expect(card?.getAttribute("href")).toBe("/inbox?filter=waiting&c=c-2");
  });

  it("does not invent a balance without an allocation", () => {
    view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null, month_days_left: 24, runs_out_on: null } }) });
    expect(screen.getByText("Todavía no tienes un tope asignado")).toBeTruthy();
    expect(screen.queryByText("Todo en orden. El saldo alcanza para el mes.")).toBeNull();
  });

  it("tells a partial read apart from a failed one", () => {
    const { unmount } = view({ home: home({ errors: ["balance"], balance: null }) });
    expect(screen.getByText(/Una parte del Panel no se pudo cargar/)).toBeTruthy();
    unmount();
    view({ home: null });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Gasto del mes")).toBeNull();
  });

  it("splits the spend by agent only with more than one", () => {
    view({
      home: home({
        spend_month: {
          total_cents: 1626,
          by_agent: [
            { agent_id: "a1", name: "Agente de ventas", cents: 950 },
            { agent_id: "a2", name: "Agente de soporte", cents: 676 },
          ],
        },
      }),
    });
    expect(screen.getByText("Agente de ventas")).toBeTruthy();
    expect(screen.getByText("58 %")).toBeTruthy();
  });
  // ── Spec 045 (R4.3, R6.1): the Panel of the design ─────────────────
  it("with one agent the spend is a first-row card and the chart takes the width: no tall empty box", () => {
    const { container } = view();
    const spend = container.querySelector('[data-slot="lite-spend"]');
    expect(spend?.parentElement?.className ?? "").not.toContain("row-span-2");
    const chart = screen.getByRole("heading", { name: "Conversaciones por día" }).closest('[data-slot="section"]');
    expect(chart?.className).toContain("lg:col-span-3");
  });

  it("with the split by agent the spend card runs down both rows, beside the chart", () => {
    const split = {
      total_cents: 1626,
      by_agent: [
        { agent_id: "a1", name: "Agente de ventas", cents: 950 },
        { agent_id: "a2", name: "Agente de soporte", cents: 676 },
      ],
    };
    const { container } = view({ home: home({ spend_month: split }) });
    expect(container.querySelector('[data-slot="lite-spend"]')?.parentElement?.className).toContain("lg:row-span-2");
    const chart = screen.getByRole("heading", { name: "Conversaciones por día" }).closest('[data-slot="section"]');
    expect(chart?.className).toContain("lg:col-span-2");
  });

  it("opens with the business over «Hola», closed by a line under the header", () => {
    const { container } = view();
    const header = container.querySelector('[data-slot="page-header"]');
    expect(header?.className).toContain("border-b");
    expect(header?.textContent).toContain("Flor y Encanto");
    expect(within(header as HTMLElement).getByRole("heading", { level: 1, name: "Hola, Valeria" })).toBeTruthy();
  });

  it("makes conversations the one dark card, with its curve along the edge", () => {
    const { container } = view();
    const card = container.querySelector('[data-slot="highlight-metric"]');
    expect(card?.textContent).toContain("Conversaciones");
    expect(card?.textContent).toContain("75");
    expect(card?.className).toContain("overflow-hidden");
    expect(card?.querySelector('[data-slot="sparkline"]')?.getAttribute("aria-label")).toBe("Conversaciones por día de los últimos 7 días");
    expect(card?.getAttribute("href")).toBe("/inbox");
  });

  it("says the balance covers N of the month's M days, M as the API counts it", () => {
    const { container } = view({ home: home({ balance: { ...home().balance!, days_left: 11.4, month_days_left: 10 } }) });
    expect(screen.getAllByText("Cubre 10 de 10 días del mes").length).toBeGreaterThan(0);
    // What a screen reader hears from the bar is the same sentence.
    expect(container.querySelector("progress")?.getAttribute("aria-valuetext")).toBe("Cubre 10 de 10 días del mes");
    expect(container.querySelector('[data-slot="meter"]')?.getAttribute("data-tone")).toBe("warning");
  });

  it("tones the bar by how long the balance lasts: alarm under 7 days, warning under 14, primary otherwise", () => {
    const tone = (days_left: number) => {
      const { container, unmount } = view({ home: home({ balance: { ...home().balance!, days_left } }) });
      const t = container.querySelector('[data-slot="meter"]')?.getAttribute("data-tone");
      unmount();
      return t;
    };
    expect(tone(4.6)).toBe("danger");
    expect(tone(11.4)).toBe("warning");
    expect(tone(30)).toBe("positive");
    view();
    expect(screen.getAllByText("Cubre 11 de 24 días del mes").length).toBeGreaterThan(0);
  });

  it("a used-up balance is an empty bar in the alarm tone, and says the agent stopped", () => {
    const { container } = view({
      home: home({ balance: { ...home().balance!, remaining_cents: 0, days_left: 0, runs_out_on: "2026-10-08" } }),
    });
    expect(screen.getAllByText("Cubre 0 de 24 días del mes").length).toBeGreaterThan(0);
    expect(container.querySelector('[data-slot="meter"]')?.getAttribute("data-tone")).toBe("danger");
    expect(screen.getByText("Saldo agotado: el agente no responde")).toBeTruthy();
  });

  it("draws no bar without spend: there is no pace to measure", () => {
    const { container } = view({ home: home({ balance: { ...home().balance!, days_left: null, runs_out_on: null } }) });
    expect(container.querySelector('[data-slot="meter"]')).toBeNull();
    expect(screen.getByText("Sin gasto en los últimos 7 días")).toBeTruthy();
  });

  it("charts conversations per day with their daily average", () => {
    view();
    expect(screen.getByRole("heading", { name: "Conversaciones por día" })).toBeTruthy();
    expect(screen.getByText("Media 11 al día")).toBeTruthy();
  });

  it("all in order says both halves only when the client has an inbox", () => {
    view();
    expect(screen.getByText("Todo en orden. Nada espera a una persona y el saldo alcanza para el mes.")).toBeTruthy();
    expect(screen.queryByText(/Comprar/)).toBeNull();
  });
});
