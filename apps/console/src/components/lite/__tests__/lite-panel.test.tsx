import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { LiteHome } from "@/lib/backend/lite";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const { LitePanelView } = await import("../lite-panel-view");

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const NOW = new Date("2026-10-08T12:00:00Z");
const days = ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"];
const counts = [5, 21, 9, 7, 5, 12, 16];

function home(o: Partial<LiteHome> = {}): LiteHome {
  return {
    spend_month: { total_cents: 1626, by_agent: null },
    conversations: { last_7d: 75, prev_7d: null, daily: days.map((day, i) => ({ day, count: counts[i]! })) },
    waiting: { count: 3, first_conversation_id: "c-2" },
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11 },
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
      <LitePanelView who={who()} home={home()} contact={contact} t={t} locale="es" now={NOW} {...props} />
    </LocaleProvider>,
  );
}

/** Spec 030 (R4): the Panel of one client, in each of its states. */
describe("LitePanelView", () => {
  it("greets by first name under the business, with the client's figures", () => {
    view();
    expect(screen.getByRole("heading", { name: "Hola, Valeria" })).toBeTruthy();
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
    expect(screen.getByLabelText(/16,26/)).toBeTruthy();
    expect(screen.getByText("Esperan a una persona")).toBeTruthy();
    expect(screen.getByText("Últimos 7 días · sin semana anterior para comparar")).toBeTruthy();
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

  it("points «Atender» at the first waiting conversation", () => {
    view({ home: home({ attention: [{ kind: "waiting", count: 3, days_left: null }] }) });
    // `Button` con `render={<Link />}` es un enlace con rol de botón (base-ui).
    const attend = screen.getByRole("button", { name: "Atender" });
    expect(attend.getAttribute("href")).toBe("/inbox?c=c-2");
  });

  it("does not invent a balance without an allocation", () => {
    view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null } }) });
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
});
