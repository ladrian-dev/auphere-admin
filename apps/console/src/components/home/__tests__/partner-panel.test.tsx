import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import { t as translate, type MessageKey } from "@/i18n/messages";
import type { HomePanel } from "@/lib/backend/home-usage";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));
const money = vi.hoisted(() => ({ bagContextAction: vi.fn(), assignBalanceAction: vi.fn(), lowerBalanceAction: vi.fn(), requestBalanceAction: vi.fn(), requestBuildExtensionAction: vi.fn() }));
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
      // Spec 072 (3.1): solo las bolsas de sus clientes, que suman el total.
      total: EUR(1234.5),
      shares: [
        { kind: "client", external_client_ref: "flor-y-encanto", client_name: "Flor y Encanto", line: null, amount: EUR(900), approx: false },
        { kind: "rest", external_client_ref: null, client_name: null, line: null, amount: EUR(334.5), approx: false },
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
    expect(within(spend).getByRole("img", { name: /Flor y Encanto 900,00\s€, El resto 334,50\s€$/ })).toBeTruthy();
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

  it("sin nada que arreglar: «Nada te necesita ahora» (spec 071, 4.4)", () => {
    show(panel({ attention: [], all_serving: true }));
    expect(screen.getByText("Nada te necesita ahora.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: /Necesita tu atención/ })).toBeNull();
  });

  it("spec 071: lo del partner va en la lista sin enlace a un cliente, y se ve en sus cifras", async () => {
    const build = {
      scope: "partner" as const,
      severity: "warning" as const,
      external_client_ref: null,
      client_name: null,
      code: "build_cap_warning" as const,
      count: 1,
      action: "request_build_extension" as const,
      href: "/usage",
      data: { pct: 84, spent: EUR(52.23), cap: EUR(62) },
    };
    const account = {
      scope: "partner" as const,
      severity: "warning" as const,
      external_client_ref: null,
      client_name: null,
      code: "account_low" as const,
      count: 1,
      action: "buy_balance" as const,
      href: "/billing",
      data: { available: EUR(60), days_left: 5 },
    };
    const { container } = show(panel({ attention: [build, account, ...panel().attention!] }));
    // La tarjeta del gasto lleva el tope con su barra.
    const line = container.querySelector("[data-slot=panel-build]")!;
    expect(plain(line.textContent)).toContain("Construcción y pruebas: 52,23 € de 62,00 € (84 %)");
    expect(within(line as HTMLElement).getByRole("meter", { name: "Construcción y pruebas" })).toHaveAttribute("aria-valuenow", "84");
    // «Saldo disponible» dice que está bajo, con texto.
    expect(container.querySelector("[data-slot=panel-balance-state]")).toHaveTextContent("Saldo bajo");
    // En la lista: sin enlace a un cliente, con su texto y su arreglo.
    const region = screen.getByRole("region", { name: /Necesita tu atención/ });
    const row = region.querySelector("[data-code=build_cap_warning]") as HTMLElement;
    expect(row).toHaveAttribute("data-scope", "partner");
    expect(within(row).queryByRole("link")).toBeNull();
    expect(plain(row.textContent)).toContain("Construcción y pruebas");
    // Todas las filas con «⋯», también las de la cuenta (owner, 2026-11-22): el arreglo es su primera opción.
    expect(within(row).queryByRole("button", { name: "Pedir ampliación" })).toBeNull();
    await userEvent.click(within(row).getByRole("button", { name: /Construcción y pruebas/ }));
    money.requestBuildExtensionAction.mockResolvedValue({ ok: true, data: { status: "requested" } });
    await userEvent.click(await screen.findByRole("menuitem", { name: "Pedir ampliación" }));
    expect(money.requestBuildExtensionAction).toHaveBeenCalledTimes(1);
    expect(plain(region.querySelector("[data-code=account_low]")!.textContent)).toContain("Te queda saldo para unos 5 días a este ritmo.");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("spec 072: el gasto cuadra, Construcción va siempre en su línea y la barra del saldo es lo disponible", async () => {
    const budget = { cap: EUR(62), spent: EUR(12.4), remaining: EUR(49.6), state: "ok" as const, paid_by: "auphere" as const };
    const long = "Clínica Dental Sonrisa Perfecta de Chamberí";
    const p = panel({
      spend: {
        ...panel().spend!,
        total: EUR(100),
        shares: [{ kind: "client", external_client_ref: "clinica", client_name: long, line: null, amount: EUR(100), approx: false }],
      },
    });
    const { container, rerender } = render(
      <LocaleProvider locale="es">
        <PartnerPanel panel={p} buildBudget={budget} />
      </LocaleProvider>,
    );
    const spend = container.querySelector("[data-slot=panel-spend]") as HTMLElement;
    // 3.2 y 3.3: una parte al 100 %, con su nombre entero (sin cortar).
    expect(plain(spend.textContent)).toContain("100 %");
    const name = within(spend).getByTitle(long);
    expect(name.className).not.toContain("truncate");
    // 3.4: por debajo del 80 %, neutra y con quién la paga; sin botón.
    const line = container.querySelector("[data-slot=panel-build]") as HTMLElement;
    expect(line).toHaveAttribute("data-tone", "calm");
    expect(plain(line.textContent)).toContain("Construcción y pruebas: 12,40 € de 62,00 € · la paga Auphere hasta el tope");
    expect(within(line).getByRole("meter", { name: "Construcción y pruebas" })).toHaveAttribute("aria-valuenow", "20");
    expect(within(line).queryByRole("button")).toBeNull();
    // 2.5: la barra de «Saldo disponible» es lo disponible (60 de 74,28).
    const bar = container.querySelector("[data-slot=panel-balance-bar]") as HTMLElement;
    expect(bar).toHaveAttribute("aria-valuenow", "81");
    expect(bar.getAttribute("aria-label")?.replace(/\s/g, " ")).toBe("Disponible: 60,00 €");
    // Desde el 80 %: la línea de la 071, en ámbar, con «Pedir ampliación» (4.4).
    const warn = {
      scope: "partner" as const,
      severity: "warning" as const,
      external_client_ref: null,
      client_name: null,
      code: "build_cap_warning" as const,
      count: 1,
      action: "request_build_extension" as const,
      href: "/usage",
      data: { pct: 84, spent: EUR(52.23), cap: EUR(62) },
    };
    rerender(
      <LocaleProvider locale="es">
        <PartnerPanel panel={{ ...p, attention: [warn] }} buildBudget={budget} />
      </LocaleProvider>,
    );
    const hot = container.querySelector("[data-slot=panel-build]") as HTMLElement;
    expect(hot).toHaveAttribute("data-tone", "warn");
    expect(plain(hot.textContent)).toContain("52,23 € de 62,00 € (84 %)");
    money.requestBuildExtensionAction.mockResolvedValue({ ok: true, data: { status: "requested" } });
    await userEvent.click(within(hot).getByRole("button", { name: "Pedir ampliación" }));
    expect(money.requestBuildExtensionAction).toHaveBeenCalledTimes(1);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Saldo disponible» lleva «Recargar saldo» para quien puede comprar (owner, 2026-11-22)", async () => {
    const { container, rerender } = render(
      <LocaleProvider locale="es">
        <PartnerPanel panel={panel()} canBuy />
      </LocaleProvider>,
    );
    const balance = container.querySelector("[data-slot=panel-balance]") as HTMLElement;
    // Solo el «+»: el nombre es su etiqueta y su pista, sin texto a la vista.
    const plus = within(balance).getByRole("button", { name: "Recargar saldo" });
    expect(plus.textContent?.trim()).toBe("");
    expect(plus).toHaveAttribute("title", "Recargar saldo");
    await userEvent.click(plus);
    expect(await screen.findByRole("dialog", { name: "Comprar saldo" })).toBeInTheDocument();
    rerender(
      <LocaleProvider locale="es">
        <PartnerPanel panel={panel()} />
      </LocaleProvider>,
    );
    expect(within(container.querySelector("[data-slot=panel-balance]") as HTMLElement).queryByRole("button", { name: "Recargar saldo" })).toBeNull();
  });

  it("las conversaciones son del mes, del día 1 a hoy, contra los mismos días del mes pasado (owner, 2026-11-22)", () => {
    const days = Array.from({ length: 22 }, (_, i) => `2026-11-${String(i + 1).padStart(2, "0")}`);
    const daily = {
      period: "month" as const,
      days,
      resolved_without_person: days.map((_, i) => (i % 2 ? 2 : 1)),
      handed_to_person: days.map(() => 0),
      previous_total: 22,
    };
    const { container } = show(panel({ conversations_per_day: daily }));
    const count = container.querySelector("[data-slot=panel-count]") as HTMLElement;
    // 11 × 1 + 11 × 2 = 33, frente a 22 del mes pasado: +50 %.
    expect(plain(count.textContent)).toContain("33");
    expect(plain(count.querySelector("[data-slot=panel-period]")?.textContent)).toBe("50 % más que los mismos días del mes pasado");
    const chart = container.querySelector("[data-slot=panel-conversations]") as HTMLElement;
    expect(within(chart).getByText("Del 1 nov al 22 nov")).toBeTruthy();
    expect(chart.querySelectorAll("table tbody tr")).toHaveLength(22);
    // Sin el mes pasado con el que comparar, dice el periodo.
    const { container: first } = show(panel({ conversations_per_day: { ...daily, previous_total: 0 } }));
    expect(plain(first.querySelector("[data-slot=panel-count] [data-slot=panel-period]")?.textContent)).toBe("Del 1 nov al 22 nov");
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
