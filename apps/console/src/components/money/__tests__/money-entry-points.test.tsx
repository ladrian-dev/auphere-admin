import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientUsage } from "@/lib/backend/money-types";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/usage", useSearchParams: () => new URLSearchParams() }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const money = vi.hoisted(() => ({
  assignBalanceAction: vi.fn(),
  bagContextAction: vi.fn(),
  lowerBalanceAction: vi.fn(),
  requestBalanceAction: vi.fn(),
  bagChoicesAction: vi.fn(),
  eurUsdAction: vi.fn(),
  moveBalanceAction: vi.fn(),
  setRefillAction: vi.fn(),
  setBagCurrencyAction: vi.fn(),
  setAgentCapAction: vi.fn(),
  requestBuildExtensionAction: vi.fn(),
  confirmMigrationAction: vi.fn(),
}));
vi.mock("@/app/(console)/usage/money-actions", () => money);
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  archiveClientAction: vi.fn(),
  deleteClientV2Action: vi.fn(),
  getClientV2Action: vi.fn(),
  restoreClientAction: vi.fn(),
  updateClientV2Action: vi.fn(),
}));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { BalanceButton } = await import("../balance-button");
const { SeedRequested, resetRequested } = await import("../request-balance");
const { UsageClientsTable } = await import("../usage-clients-table");
const { AgentCapForm } = await import("../agent-cap");
const { MigrationWizard } = await import("../migration-wizard");
const { UsageLines } = await import("../usage-lines");
const { ClientMenu } = await import("@/components/clients/v2/client-menu");

/**
 * Spec 047 (T159, T160, T153): dónde se abre el dinero. «Pedir saldo» con su
 * nota y «Pedido hace…»; la tabla de Consumo con «Sin saldo» y sus acciones en
 * «⋯»; el tope del agente; la construcción con «Pedir ampliación»; el reparto en
 * bolsas; y «Asignar saldo» del ⋯ del cliente, en el sitio.
 */
const M = (n: number, currency: "EUR" | "USD" = "EUR") => ({ amount_micros: Math.round(n * 100_000), currency });
const ok = <T,>(data: T) => ({ ok: true as const, data });
const plain = (s: string | null | undefined) => (s ?? "").replace(/[  ]/g, " ").replace(/\s+/g, " ").trim();
const wrap = (ui: React.ReactNode) => render(<LocaleProvider locale="es">{ui}</LocaleProvider>);

function client(over: Partial<ClientUsage> = {}): ClientUsage {
  return { ref: "flor-y-encanto", name: "Flor y Encanto", bag: M(35.5, "USD"), month_spent: M(12.4), days_left: 9, refill_up_to: null, empty: false, ...over };
}

describe("«Pedir saldo» (45.7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetRequested();
  });

  it("una nota de hasta 280, avisa y el botón dice «Pedido hace…»", async () => {
    const user = userEvent.setup();
    money.requestBalanceAction.mockResolvedValue(ok({ status: "requested" }));
    wrap(<BalanceButton refId="flor-y-encanto" name="Flor y Encanto" mode="request" />);
    await user.click(screen.getByRole("button", { name: "Pedir saldo" }));
    const dialog = screen.getByRole("dialog", { name: "Pedir saldo para Flor y Encanto" });
    const note = within(dialog).getByRole("textbox", { name: /Nota/ });
    expect(note).toHaveAttribute("maxLength", "280");
    await user.type(note, "Se acaba el viernes");
    expect(within(dialog).getByText("19 de 280 caracteres")).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Pedir saldo" }));
    await waitFor(() => expect(money.requestBalanceAction).toHaveBeenCalledWith({ ref: "flor-y-encanto", note: "Se acaba el viernes" }));
    expect(toast.success).toHaveBeenCalledWith("Pedido. Avisamos a los owners y admins para Flor y Encanto.");
    const done = await screen.findByRole("button", { name: "Pedido hace un momento" });
    expect(done).toBeDisabled();
  });

  it("lo que la API sabe de hoy (`requested_at`) sobrevive a recargar", async () => {
    const at = new Date(Date.now() - 5 * 60_000).toISOString();
    wrap(
      <>
        <SeedRequested items={[{ ref: "flor-y-encanto", requested_at: at }]} />
        <BalanceButton refId="flor-y-encanto" name="Flor y Encanto" mode="request" />
      </>,
    );
    expect(await screen.findByRole("button", { name: "Pedido hace 5 minutos" })).toBeDisabled();
  });

  it("si ya se pidió hoy (429), lo dice y el botón queda en «Pedido hoy»", async () => {
    const user = userEvent.setup();
    money.requestBalanceAction.mockResolvedValue({ ok: false, status: 429, message: "", code: "request_already_sent_today", info: { retry_after: "tomorrow" } });
    wrap(<BalanceButton refId="flor-y-encanto" name="Flor y Encanto" mode="request" />);
    await user.click(screen.getByRole("button", { name: "Pedir saldo" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pedir saldo" }));
    expect(await screen.findByText(/Pedido hoy\. Mañana se puede volver a pedir\./)).toBeTruthy();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cerrar" }));
    expect(await screen.findByRole("button", { name: "Pedido hoy" })).toBeDisabled();
  });
});

describe("Consumo · la tabla por cliente (46.2, 45.6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetRequested();
  });

  it("su bolsa en su moneda, lo gastado, los días y el relleno; sin saldo, en rojo y con «Asignar saldo»", async () => {
    const { container } = wrap(
      <UsageClientsTable
        canWrite
        days={30}
        clients={[client({ refill_up_to: M(50, "USD") }), client({ ref: "barberia", name: "Barbería Cultor", bag: M(0), month_spent: M(0), empty: true, days_left: null })]}
      />,
    );
    const table = screen.getByRole("region", { name: "Saldo por cliente" });
    const rows = within(table).getAllByRole("row");
    expect(plain(rows[1]!.textContent)).toContain("35,50 USD");
    expect(plain(rows[1]!.textContent)).toContain("12,40 €");
    expect(plain(rows[1]!.textContent)).toContain("Unos 9 días");
    expect(plain(rows[1]!.textContent)).toContain("Hasta 50,00 USD");
    const empty = rows[2]!;
    expect(within(empty).getByText("Sin saldo").closest("[data-tone]")).toHaveAttribute("data-tone", "danger");
    // Regla de los tres puntos: «Asignar saldo» va en el ⋯, no repetido junto al estado.
    expect(within(empty).queryByRole("button", { name: "Asignar saldo" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin saldo, «Asignar saldo» se abre desde el ⋯ de ese cliente", async () => {
    const user = userEvent.setup();
    wrap(<UsageClientsTable canWrite days={30} clients={[client(), client({ ref: "barberia", name: "Barbería Cultor", bag: M(0), month_spent: M(0), empty: true, days_left: null })]} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    expect((await screen.findAllByRole("menuitem"))[0]).toHaveTextContent("Asignar saldo");
  });

  it("el ⋯ de cada cliente: «Cambiar saldo», «Mover saldo a otro cliente» y «Ver su gasto»", async () => {
    const user = userEvent.setup();
    wrap(<UsageClientsTable canWrite days={7} clients={[client(), client({ ref: "barberia", name: "Barbería Cultor" })]} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    expect(items).toEqual(["Cambiar saldo", "Mover saldo a otro cliente", "Ver su gasto", "Relleno mensual", "Cambiar la moneda", "Abrir ficha del cliente"]);
    expect(screen.getByRole("menuitem", { name: "Ver su gasto" })).toHaveAttribute("href", "/usage?client=flor-y-encanto&days=7#gasto");
    // «tope» es solo del agente (45.6).
    expect(items.join(" ")).not.toMatch(/tope/i);
  });

  it("«Cambiar saldo» abre el modal aquí mismo", async () => {
    const user = userEvent.setup();
    money.bagContextAction.mockResolvedValue(
      ok({
        bag: { ref: "flor-y-encanto", balance: M(35.5, "USD"), month_spent: M(1, "USD"), month_base: M(36.5, "USD"), days_left: 9, state: "ok", refill_up_to: null, alert_low: true },
        available: M(100, "USD"),
        eurUsd: null,
        canRecharge: true,
        bagsActive: true,
      }),
    );
    wrap(<UsageClientsTable canWrite days={30} clients={[client(), client({ ref: "barberia", name: "Barbería Cultor" })]} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cambiar saldo" }));
    expect(await screen.findByRole("dialog", { name: "Cambiar el saldo de Flor y Encanto" })).toBeTruthy();
    expect(money.bagContextAction).toHaveBeenCalledWith({ ref: "flor-y-encanto" });
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("quien no puede asignar ve «Pedir saldo», «Ver su gasto» y la ficha, nada más", async () => {
    const user = userEvent.setup();
    wrap(<UsageClientsTable canWrite={false} days={30} clients={[client(), client({ ref: "barberia", name: "Barbería Cultor", bag: null, empty: true })]} />);
    expect(screen.queryByRole("button", { name: "Asignar saldo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Pedir saldo" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Pedir saldo", "Ver su gasto", "Abrir ficha del cliente"]);
  });
});

describe("el tope del agente (44.1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("se escribe con coma, en la moneda de la bolsa, y se puede quitar", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async (body: { cap: { amount_micros: number } | null }) =>
      ok({ agent_id: "00000000-0000-4000-8000-0000000000a1", monthly_cap_micros: body.cap ? body.cap.amount_micros : null, lifecycle: "published" }),
    );
    wrap(<AgentCapForm refId="flor-y-encanto" agentId="00000000-0000-4000-8000-0000000000a1" agentName="Citas" cap={undefined} currency="USD" canWrite actions={{ save }} />);
    expect(screen.getByText(/No podemos leer el tope de hoy/)).toBeTruthy();
    // Con lo gastado del mes, se dice al lado.
    await user.type(screen.getByRole("textbox", { name: "Tope mensual, en USD" }), "25,5");
    await user.click(screen.getByRole("button", { name: "Guardar el tope" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ ref: "flor-y-encanto", agent: "00000000-0000-4000-8000-0000000000a1", cap: M(25.5, "USD") }));
    expect(plain(toast.success.mock.calls[0]?.[0] as string)).toBe("Tope de Citas: 25,50 USD al mes.");
    expect(plain(screen.getByText(/Tope de hoy/).textContent)).toBe("Tope de hoy: 25,50 USD al mes.");
    await user.click(screen.getByRole("button", { name: "Quitar el tope" }));
    await waitFor(() => expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ cap: null })));
    expect(await screen.findByText(/Sin tope: gasta de la bolsa/)).toBeTruthy();
  });

  it("con el tope y lo gastado de la cabecera del agente", () => {
    wrap(<AgentCapForm refId="r" agentId="00000000-0000-4000-8000-0000000000a1" agentName="Citas" cap={M(30, "USD")} spent={M(12.4, "USD")} currency="USD" canWrite />);
    expect(plain(screen.getByText(/Tope de hoy/).textContent)).toBe("Tope de hoy: 30,00 USD al mes. Este mes lleva 12,40 USD.");
    expect(screen.getByRole("textbox", { name: "Tope mensual, en USD" })).toHaveValue("30,00");
  });

  it("quien no puede fijarlo solo lo lee", () => {
    wrap(<AgentCapForm refId="r" agentId="00000000-0000-4000-8000-0000000000a1" agentName="Citas" cap={M(10, "EUR")} currency="EUR" canWrite={false} />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(plain(screen.getByText(/Tope de hoy/).textContent)).toBe("Tope de hoy: 10,00 € al mes.");
  });
});

describe("las partidas (46.4, 46.5)", () => {
  it("cada una con quién paga, y la construcción con su tope en dinero y «Pedir ampliación»", async () => {
    const user = userEvent.setup();
    const requestMore = vi.fn(async () => ok({ status: "requested" }));
    const { container } = wrap(
      <UsageLines
        lines={[
          { line: "conversations", amount: M(30), payer: "client_bag", approx: false },
          { line: "meta", amount: M(4), payer: "business_meta", approx: true },
          { line: "build", amount: M(42), payer: "auphere", approx: false, cap: M(50), state: "warning" },
          { line: "companion", amount: M(2), payer: "account", approx: false },
        ]}
        build={{ cap: M(50), spent: M(42), remaining: M(8), state: "warning", paid_by: "auphere" }}
        actions={{ requestMore }}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items.map((i) => i.querySelector("h3")?.textContent)).toEqual(["Conversaciones", "Mensajes de Meta", "Construcción y pruebas", "Companion y teammates"]);
    expect(plain(items[1]!.textContent)).toContain("aprox. 4,00 €");
    expect(items[1]!.textContent).toMatch(/La paga el negocio, a Meta/);
    expect(plain(items[2]!.textContent)).toContain("42,00 € de 50,00 € · 84 %");
    expect(items[2]!.textContent).toMatch(/más del 80 %/);
    expect(container.textContent).not.toMatch(/tokens?/i);
    expect(await axeViolations(container)).toEqual([]);
    await user.click(within(items[2]!).getByRole("button", { name: "Pedir ampliación" }));
    await waitFor(() => expect(requestMore).toHaveBeenCalled());
    expect(within(items[2]!).getAllByText("Pedido a Auphere. Te avisamos cuando suba el tope.").length).toBeGreaterThan(0);
  });
});

describe("«Repartir tu saldo en bolsas» (55.3)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("enseña lo que le queda a cada cliente y confirma", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn(async () => ok({ status: "confirmed" as const, clients: 2 }));
    wrap(
      <MigrationWizard
        proposal={{ confirmed_at: null, clients: [{ ref: "flor-y-encanto", amount: M(12.5, "USD") }, { ref: "barberia", amount: M(7, "USD") }] }}
        names={{ "flor-y-encanto": "Flor y Encanto", barberia: "Barbería Cultor" }}
        canConfirm
        actions={{ confirm }}
      />,
    );
    const table = screen.getByRole("region", { name: "La propuesta por cliente" });
    expect(plain(table.textContent)).toContain("Flor y Encanto12,50 USD");
    expect(plain(table.textContent)).toContain("Total19,50 USD");
    expect(screen.getByText(/siguen respondiendo con el límite de hoy/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Confirmar el reparto" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    expect(await screen.findAllByText("Listo: 2 clientes tienen ya su bolsa.")).not.toHaveLength(0);
  });

  it("se puede ajustar antes de confirmar: solo va lo que cambió", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn(async () => ok({ status: "confirmed" as const, clients: 2 }));
    wrap(
      <MigrationWizard
        proposal={{ confirmed_at: null, clients: [{ ref: "flor-y-encanto", amount: M(12.5, "USD") }, { ref: "barberia", amount: M(7, "USD") }] }}
        names={{ "flor-y-encanto": "Flor y Encanto", barberia: "Barbería Cultor" }}
        canConfirm
        currency="USD"
        actions={{ confirm }}
      />,
    );
    const field = screen.getByRole("textbox", { name: "Lo que pasa a la bolsa de Barbería Cultor, en USD" });
    await user.clear(field);
    await user.type(field, "20,5");
    expect(plain(document.querySelector("[data-slot=migration-total]")?.textContent)).toBe("33,00 USD");
    await user.click(screen.getByRole("button", { name: "Confirmar el reparto" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith({ adjust: { barberia: 2_050_000 } }));
  });

  it("sin permiso, se ve la propuesta pero la confirma un owner o un admin", () => {
    wrap(<MigrationWizard proposal={{ confirmed_at: null, clients: [{ ref: "a", amount: M(1, "USD") }] }} names={{}} canConfirm={false} />);
    expect(screen.queryByRole("button", { name: "Confirmar el reparto" })).toBeNull();
    expect(screen.getByText("Lo confirma un owner o un admin de tu equipo.")).toBeTruthy();
  });
});

describe("el ⋯ del cliente abre el dinero en el sitio (45.1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetRequested();
  });

  it("«Asignar saldo» abre el modal, sin enlace a otra pantalla", async () => {
    const user = userEvent.setup();
    money.bagContextAction.mockResolvedValue({ ok: false, status: 500, message: "boom", code: null });
    wrap(<ClientMenu refId="flor-y-encanto" name="Flor y Encanto" allowed={["edit", "assign_balance", "archive"]} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    const item = await screen.findByRole("menuitem", { name: "Asignar saldo" });
    expect(item).not.toHaveAttribute("href");
    await user.click(item);
    expect(await screen.findByRole("dialog", { name: "Asignar saldo a Flor y Encanto" })).toBeTruthy();
    // Si la lectura falla, se dice y se puede reintentar.
    expect(await screen.findByText("No se pudo hacer. Inténtalo de nuevo.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeTruthy();
  });

  it("«Pedir saldo» abre su ventana para quien no asigna", async () => {
    const user = userEvent.setup();
    wrap(<ClientMenu refId="flor-y-encanto" name="Flor y Encanto" allowed={["edit", "request_balance"]} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    await user.click(await screen.findByRole("menuitem", { name: "Pedir saldo" }));
    expect(await screen.findByRole("dialog", { name: "Pedir saldo para Flor y Encanto" })).toBeTruthy();
  });

  it("al archivar con saldo en la bolsa ofrece devolverlo a la cuenta (43.13)", async () => {
    const user = userEvent.setup();
    const archive = vi.fn(async () => ok({ ref: "flor-y-encanto", lifecycle: "archived" as const, previous: "active" as const, agents: [], undo: "restore" as const, bag_left: M(12.34, "USD") }));
    money.lowerBalanceAction.mockResolvedValue(ok({}));
    wrap(<ClientMenu refId="flor-y-encanto" name="Flor y Encanto" allowed={["edit", "assign_balance", "archive"]} actions={{ archive }} />);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    // Como el prototipo, archivar no pregunta: se hace al momento y se deshace con «Deshacer».
    await user.click(await screen.findByRole("menuitem", { name: "Archivar" }));
    const offer = await screen.findByRole("dialog", { name: "Devolver a la cuenta" });
    expect(plain(offer.textContent)).toContain("A Flor y Encanto le quedan 12,34 USD en su bolsa.");
    await user.click(within(offer).getByRole("button", { name: "Devolver a la cuenta" }));
    await waitFor(() => expect(money.lowerBalanceAction).toHaveBeenCalledWith(expect.objectContaining({ ref: "flor-y-encanto", amount: M(12.34, "USD") })));
  });
});
