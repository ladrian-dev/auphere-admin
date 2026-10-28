import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import { t as translate, type MessageKey } from "@/i18n/messages";
import type { HomePanel } from "@/lib/backend/home-usage";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));
const money = vi.hoisted(() => ({ bagContextAction: vi.fn(), assignBalanceAction: vi.fn(), lowerBalanceAction: vi.fn(), requestBalanceAction: vi.fn() }));
vi.mock("@/app/(console)/usage/money-actions", () => money);

const { PartnerPanel } = await import("../partner-panel");
const { attentionFix, conversationColumns, conversationTotal, monthPeriod, shareLabel } = await import("../panel-model");

/**
 * Spec 047 (T163, requisito 48): el Panel del partner con la consola nueva. Cada
 * bloque dice su periodo; «Necesita tu atención» arregla el saldo en el sitio y
 * lleva lo demás a su pantalla; sin nada que arreglar, «Todos tus clientes están
 * atendiendo»; la gráfica de conversaciones lleva su tabla. Pasa axe.
 */
const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const EUR = (n: number) => ({ amount_micros: Math.round(n * 100_000), currency: "EUR" as const });
const plain = (s: string | null | undefined) => (s ?? "").replace(/[  ]/g, " ").replace(/\s+/g, " ").trim();

function panel(over: Partial<HomePanel> = {}): HomePanel {
  return {
    spend: {
      period: "month",
      since: "2026-10-01T00:00:00Z",
      until: "2026-11-01T00:00:00Z",
      total: EUR(1234.5),
      shares: [
        { kind: "client", external_client_ref: "flor-y-encanto", client_name: "Flor y Encanto", line: null, amount: EUR(900), approx: false },
        { kind: "rest", external_client_ref: null, client_name: null, line: null, amount: EUR(300), approx: false },
        { kind: "line", external_client_ref: null, client_name: null, line: "companion", amount: EUR(34.5), approx: false },
      ],
    },
    clients: { period: "now", serving: 7, not_archived: 9, onboarding: 1 },
    balance: { period: "now", available: EUR(60), in_bags: EUR(14.28), in_bags_approx: true },
    conversations_per_day: {
      period: "7d",
      days: ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"],
      resolved_without_person: [10, 12, 0, 4, 8, 9, 3],
      handed_to_person: [1, 0, 0, 2, 1, 1, 0],
    },
    attention: [
      { external_client_ref: "barberia-cultor", client_name: "Barbería Cultor", code: "no_balance", count: 1, action: "assign_balance", href: "/clients/barberia-cultor?assign=1" },
      { external_client_ref: "flor-y-encanto", client_name: "Flor y Encanto", code: "channel_problem", count: 2, action: "fix_channel", href: "/clients/flor-y-encanto/agents" },
    ],
    all_serving: false,
    errors: [],
    ...over,
  };
}

const show = (p: HomePanel) =>
  render(
    <LocaleProvider locale="es">
      <PartnerPanel panel={p} />
    </LocaleProvider>,
  );

describe("PartnerPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("cada bloque con su periodo: el gasto repartido, los clientes, el saldo y las conversaciones con su tabla", async () => {
    const { container } = show(panel());
    const spend = container.querySelector("[data-slot=panel-spend]") as HTMLElement;
    expect(within(spend).getByText("Del 1 oct al 31 oct")).toBeTruthy();
    expect(plain(spend.textContent)).toContain("1.234,50 €");
    expect(within(spend).getByRole("img", { name: /Flor y Encanto 900,00\s€, El resto 300,00\s€, Companion y teammates 34,50\s€/ })).toBeTruthy();
    const clients = container.querySelector("[data-slot=panel-clients]") as HTMLElement;
    expect(within(clients).getByText("Clientes atendiendo")).toBeTruthy();
    expect(plain(clients.textContent)).toContain("7");
    expect(plain(clients.textContent)).toContain("De 9 · 1 en alta");
    const balance = container.querySelector("[data-slot=panel-balance]") as HTMLElement;
    expect(within(balance).getByText("Saldo disponible")).toBeTruthy();
    expect(plain(balance.textContent)).toContain("60,00 €");
    expect(plain(balance.textContent)).toContain("aprox. 14,28 € asignado a clientes");
    const count = container.querySelector("[data-slot=panel-count]") as HTMLElement;
    expect(within(count).getByText("Conversaciones")).toBeTruthy();
    expect(plain(count.textContent)).toContain("51");
    const conversations = container.querySelector("[data-slot=panel-conversations]") as HTMLElement;
    expect(within(conversations).getByText("Últimos 7 días")).toBeTruthy();
    // Como el prototipo: el total está en la cifra de arriba, la gráfica no lo repite.
    expect(within(conversations).queryByText("51 conversaciones", { selector: "p" })).toBeNull();
    expect(within(conversations).getByRole("listbox", { name: "Conversaciones por día" })).toBeTruthy();
    const table = conversations.querySelector("table") as HTMLElement;
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("como el prototipo: arriba el gasto y las cifras, luego la gráfica y al final lo que necesita atención", () => {
    const { container } = show(panel());
    const order = Array.from(container.querySelectorAll("[data-slot^=panel-]"))
      .map((el) => el.getAttribute("data-slot"))
      .filter((slot) => ["panel-spend", "panel-count", "panel-clients", "panel-balance", "panel-conversations", "panel-attention"].includes(slot ?? ""));
    expect(order).toEqual(["panel-spend", "panel-count", "panel-clients", "panel-balance", "panel-conversations", "panel-attention"]);
    // 9 clientes, 2 con algo que arreglar: «7 de 9 clientes sin problemas».
    const attention = screen.getByRole("region", { name: /Necesita tu atención/ });
    expect(within(attention).getByText("7 de 9 clientes sin problemas.")).toBeTruthy();
  });

  it("«Necesita tu atención»: el arreglo es la primera opción del «⋯», el saldo se asigna aquí mismo y lo demás lleva a su pantalla", async () => {
    const user = userEvent.setup();
    money.bagContextAction.mockResolvedValue({ ok: false, status: 500, message: "", code: null });
    show(panel());
    const section = screen.getByRole("region", { name: /Necesita tu atención/ });
    const rows = within(section).getAllByRole("listitem");
    expect(within(rows[0]!).getByText("Sin saldo")).toBeTruthy();
    // Andrés, 2026-10-28: sin botones sueltos en la fila, todo dentro del «⋯».
    expect(within(rows[0]!).queryByRole("button", { name: "Asignar saldo" })).toBeNull();
    await user.click(within(rows[1]!).getByRole("button", { name: /Más acciones de/ }));
    const channelMenu = await screen.findByRole("menu");
    const [first] = within(channelMenu).getAllByRole("menuitem");
    expect(first).toHaveTextContent("Arreglar el canal");
    expect(first).toHaveAttribute("href", "/clients/flor-y-encanto/agents");
    await user.keyboard("{Escape}");
    await user.click(within(rows[0]!).getByRole("button", { name: /Más acciones de/ }));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Asignar saldo" }));
    expect(await screen.findByRole("dialog", { name: "Asignar saldo a Barbería Cultor" })).toBeTruthy();
    expect(money.bagContextAction).toHaveBeenCalledWith({ ref: "barberia-cultor" });
  });

  it("quien no asigna ve «Pedir saldo» como primera opción del «⋯»", async () => {
    const user = userEvent.setup();
    show(panel({ attention: [{ external_client_ref: "barberia-cultor", client_name: "Barbería Cultor", code: "no_balance", count: 1, action: "request_balance", href: "/clients/barberia-cultor" }] }));
    await user.click(screen.getByRole("button", { name: /Más acciones de/ }));
    const [first] = within(await screen.findByRole("menu")).getAllByRole("menuitem");
    expect(first).toHaveTextContent("Pedir saldo");
  });

  it("como el prototipo: la semana frente a la anterior bajo las conversaciones, y cifras de 28 px", () => {
    const { container } = render(
      <LocaleProvider locale="es">
        <PartnerPanel panel={panel()} trend={{ current: 51, previous: 40 }} />
      </LocaleProvider>,
    );
    const count = container.querySelector("[data-slot=panel-count]") as HTMLElement;
    expect(within(count).getByText("28 % más que los 7 días anteriores")).toBeVisible();
    expect(within(count).getByText("51").className).toMatch(/text-\[28px\]/);
  });

  it("«Necesita tu atención» enseña cuatro y deja ver el resto", async () => {
    const user = userEvent.setup();
    const row = (n: number) => ({ external_client_ref: `c${n}`, client_name: `Cliente ${n}`, code: "low_balance" as const, count: 1, action: "assign_balance" as const, href: `/clients/c${n}` });
    show(panel({ attention: [1, 2, 3, 4, 5, 6].map(row) }));
    const region = screen.getByRole("region", { name: /Necesita tu atención/ });
    expect(within(region).getAllByRole("listitem")).toHaveLength(4);
    await user.click(within(region).getByRole("button", { name: "Ver 2 más" }));
    expect(within(region).getAllByRole("listitem")).toHaveLength(6);
    expect(within(region).getByRole("button", { name: "Ver menos" })).toBeVisible();
  });

  it("sin nada que arreglar: «Todos tus clientes están atendiendo»", () => {
    show(panel({ attention: [], all_serving: true }));
    expect(screen.getByText("Todos tus clientes están atendiendo.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: /Necesita tu atención/ })).toBeNull();
  });

  it("si un bloque no se pudo leer, lo dice y no pinta ceros", () => {
    show(panel({ balance: null, spend: null, errors: ["money"] }));
    expect(screen.getByText(/Alguno de los bloques no se pudo leer/)).toBeTruthy();
    expect(document.querySelector("[data-slot=panel-balance]")).toBeNull();
    expect(document.querySelector("[data-slot=panel-spend]")).toBeNull();
  });
});

describe("el modelo del Panel", () => {
  it("el periodo del mes, con `until` exclusivo", () => {
    expect(monthPeriod(t, "2026-10-01T00:00:00Z", "2026-11-01T00:00:00Z")).toBe("Del 1 oct al 31 oct");
  });

  it("cada parte del gasto se llama por su cliente, «El resto» o su partida", () => {
    const base = { external_client_ref: null, client_name: null, line: null, amount: EUR(1), approx: false } as const;
    expect(shareLabel(t, { ...base, kind: "client", external_client_ref: "x", client_name: "Lola" })).toBe("Lola");
    expect(shareLabel(t, { ...base, kind: "rest" })).toBe("El resto");
    expect(shareLabel(t, { ...base, kind: "line", line: "meta" })).toBe("Mensajes de Meta");
  });

  it("las columnas de conversaciones: dos series, una por día, y «Hoy» al final", () => {
    const daily = panel().conversations_per_day!;
    const cols = conversationColumns(t, daily);
    expect(cols).toHaveLength(7);
    expect(cols[0]).toMatchObject({ key: "2026-10-22", label: "jue", values: [10, 1] });
    expect(cols[6]!.label).toBe("Hoy");
    expect(conversationTotal(daily)).toBe(51);
  });

  it("el arreglo de cada fila: el saldo en el sitio, lo demás con su enlace", () => {
    const row = panel().attention![1]!;
    expect(attentionFix({ ...row, action: "assign_balance" })).toEqual({ kind: "assign" });
    expect(attentionFix({ ...row, action: "request_balance" })).toEqual({ kind: "request" });
    expect(attentionFix({ ...row, action: "raise_cap", href: "/clients/x/agents/a?tab=advanced" })).toEqual({
      kind: "link",
      href: "/clients/x/agents/a?tab=advanced",
      label: "panel.v2.fix.raise_cap",
    });
  });
});
