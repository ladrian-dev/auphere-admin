import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { BagContext, Receipt } from "@/lib/backend/money-types";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/usage/money-actions", () => ({
  assignBalanceAction: vi.fn(),
  bagContextAction: vi.fn(),
  lowerBalanceAction: vi.fn(),
}));

const { AssignDialog } = await import("../assign-dialog");

/**
 * Spec 047 (T159, T153; requisito 45): el modal «Asignar saldo a {cliente}».
 * Las cantidades rápidas en la moneda de la bolsa y «Otra cantidad» con coma;
 * el recibo anunciado, con la línea del BCE si las monedas son distintas;
 * «Faltan» con «Recargar mi cuenta» solo para quien compra y el botón
 * desactivado; el aviso ámbar; la casilla del 20 % marcada; el aviso final; y
 * «Cambiar saldo» para bajar. Pasa axe.
 */
const M = (n: number, currency: "EUR" | "USD") => ({ amount_micros: Math.round(n * 100_000), currency });
const plain = (s: string | null | undefined) => (s ?? "").replace(/[  ]/g, " ").replace(/\s+/g, " ").trim();
const ok = <T,>(data: T) => ({ ok: true as const, data });

function ctx(over: Partial<BagContext> = {}): BagContext {
  return {
    bag: {
      ref: "flor-y-encanto",
      balance: M(15.5, "USD"),
      month_spent: M(4, "USD"),
      month_base: M(19.5, "USD"),
      days_left: 9,
      state: "ok",
      refill_up_to: null,
      alert_low: true,
    },
    available: M(240, "EUR"),
    eurUsd: { rate: "1.0852", date: "2026-10-26", source: "ECB" },
    canRecharge: true,
    bagsActive: true,
    ...over,
  };
}

const RECEIPT: Receipt = {
  client_balance_before: M(15.5, "USD"),
  assigned: M(20, "USD"),
  debited_from_account: M(18.43, "EUR"),
  fx: { rate: "1.0852", date: "2026-10-26", source: "ECB" },
  client_balance_after: M(35.5, "USD"),
  account_left: M(221.48, "EUR"),
  warn_low_account: false,
};

function open(context: BagContext, over: Record<string, unknown> = {}, props: { change?: boolean } = {}) {
  const actions = {
    context: vi.fn(async () => ok(context)),
    assign: vi.fn(async () => ok(RECEIPT)),
    lower: vi.fn(async () => ok({ ...context.bag, balance: M(10.5, "USD") })),
    ...over,
  };
  const onOpenChange = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <AssignDialog refId="flor-y-encanto" name="Flor y Encanto" onOpenChange={onOpenChange} actions={actions as never} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions, onOpenChange, user: userEvent.setup() };
}

const receipt = () => document.querySelector("[data-slot=assign-receipt]") as HTMLElement;
const row = (label: RegExp | string) => {
  const dt = within(receipt()).getByText(label, { selector: "dt, dt *" });
  return plain(dt.closest("div")?.querySelector("dd")?.textContent);
};

describe("AssignDialog · «Asignar saldo a {cliente}»", () => {
  beforeEach(() => vi.clearAllMocks());

  it("cantidades rápidas en la moneda de la bolsa y el recibo con la línea del BCE (45.2)", async () => {
    const { user } = open(ctx());
    const dialog = await screen.findByRole("dialog", { name: "Asignar saldo a Flor y Encanto" });
    const radios = within(dialog).getAllByRole("radio");
    expect(radios.map((r) => plain(r.closest("label")?.textContent))).toEqual(["10,00 USD", "20,00 USD", "50,00 USD", "100,00 USD", "Otra cantidad"]);
    expect(radios[1]).toBeChecked();
    // El recibo se anuncia.
    const box = receipt();
    expect(box.getAttribute("role")).toBe("status");
    expect(box.getAttribute("aria-live")).toBe("polite");
    expect(row("Saldo actual de Flor y Encanto")).toBe("15,50 USD");
    expect(row("Asignas")).toBe("20,00 USD");
    expect(row(/Sale de tu cuenta/)).toBe("18,43 €");
    expect(within(box).getByText("1 € = 1,0852 USD · BCE 26 oct 2026")).toBeTruthy();
    expect(row("Nuevo saldo")).toBe("35,50 USD");
    expect(row("Queda en tu cuenta")).toBe("221,57 €");
    // La casilla del 20 %, marcada; el relleno, no.
    expect(within(dialog).getByRole("checkbox", { name: "Avisarme cuando le quede menos del 20 %" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Rellenar cada mes hasta…" })).not.toBeChecked();
    expect(await axeViolations()).toEqual([]);
    await user.click(radios[3]!);
    expect(row("Asignas")).toBe("100,00 USD");
  });

  it("«Otra cantidad» admite coma decimal y lo que no es un importe se dice en su campo", async () => {
    const { user } = open(ctx({ eurUsd: null, available: M(500, "USD") }));
    await user.click(await screen.findByRole("radio", { name: "Otra cantidad" }));
    const field = screen.getByRole("textbox", { name: "Otra cantidad, en USD" });
    await user.type(field, "12,5");
    expect(row("Asignas")).toBe("12,50 USD");
    expect(row("Sale de tu cuenta")).toBe("12,50 USD");
    expect(within(receipt()).queryByText(/BCE/)).toBeNull();
    await user.clear(field);
    await user.type(field, "12,505");
    expect(screen.getByText("Escribe un importe como 25 o 25,50.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asignar saldo" })).toBeDisabled();
  });

  it("si no llega: «Faltan» en rojo, «Recargar mi cuenta» con lo que falta y el botón desactivado (45.3)", async () => {
    const { user, actions } = open(ctx({ eurUsd: null, available: M(30, "USD") }));
    await user.click(await screen.findByRole("radio", { name: /^50,00\sUSD$/ }));
    const missing = screen.getByText("Faltan 20,00 USD");
    expect(missing.className).toContain("text-destructive");
    expect(screen.getByRole("link", { name: "Recargar mi cuenta" })).toHaveAttribute("href", "/billing?recargar=20");
    expect(screen.getByRole("button", { name: "Asignar saldo" })).toBeDisabled();
    expect(actions.assign).not.toHaveBeenCalled();
  });

  it("quien no compra no ve «Recargar mi cuenta»: se le dice a quién pedirlo", async () => {
    const { user } = open(ctx({ eurUsd: null, available: M(30, "USD"), canRecharge: false }));
    await user.click(await screen.findByRole("radio", { name: /^100,00\sUSD$/ }));
    expect(screen.getByText("Faltan 70,00 USD")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Recargar mi cuenta" })).toBeNull();
    expect(screen.getByText(/Pide a quien lleva la facturación/)).toBeTruthy();
  });

  it("si la cuenta se queda con menos del 20 %: aviso ámbar, sin bloquear (45.4)", async () => {
    const { user } = open(ctx({ eurUsd: null, available: M(110, "USD") }));
    await user.click(await screen.findByRole("radio", { name: /^100,00\sUSD$/ }));
    const amber = document.querySelector("[data-slot=assign-low]");
    expect(plain(amber?.textContent)).toBe("Tu cuenta se queda con menos del 20 % de lo que tenía.");
    expect(amber?.className).toContain("bg-status-warning-bg");
    expect(screen.getByRole("button", { name: "Asignar saldo" })).toBeEnabled();
  });

  it("asignar manda el importe en la moneda de la bolsa, la casilla y la clave, y avisa con lo que queda (45.5)", async () => {
    const { user, actions, onOpenChange } = open(ctx());
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("checkbox", { name: "Rellenar cada mes hasta…" }));
    await user.type(screen.getByRole("textbox", { name: "Hasta, en USD" }), "40");
    await user.click(screen.getByRole("button", { name: "Asignar saldo" }));
    await waitFor(() => expect(actions.assign).toHaveBeenCalledTimes(1));
    const body = (actions.assign.mock.calls[0] as unknown[])[0] as Record<string, unknown>;
    expect(body).toMatchObject({ ref: "flor-y-encanto", amount: M(20, "USD"), refill_up_to: M(40, "USD"), alert_low: true });
    expect(String(body.key)).toMatch(/^assign:/);
    expect(plain(toast.success.mock.calls[0]?.[0] as string)).toBe("Asignados 20,00 USD a Flor y Encanto. En tu cuenta quedan 221,48 €.");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(nav.refresh).toHaveBeenCalled();
  });

  it("si la API dice que falta, se enseña «Faltan» con su cifra y no se reintenta solo", async () => {
    const assign = vi.fn(async () => ({ ok: false as const, status: 409, message: "", code: "insufficient_account", info: { available_micros: 1_000_000, currency: "EUR", missing_micros: 843_000 } }));
    const { user } = open(ctx(), { assign });
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Asignar saldo" }));
    expect(await screen.findByText("Faltan 8,43 €")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asignar saldo" })).toBeDisabled();
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it("si el partner aún no tiene bolsas, lleva a «Repartir tu saldo en bolsas» (55.3)", async () => {
    open(ctx({ bagsActive: false }));
    await screen.findByRole("dialog");
    expect(screen.getByText("Repartir tu saldo en bolsas").closest("a")).toHaveAttribute("href", "/usage/repartir");
    expect(screen.getByRole("button", { name: "Asignar saldo" })).toBeDisabled();
  });

  it("«Cambiar saldo» deja devolver a la cuenta lo que queda, y no más (43.6)", async () => {
    const { user, actions } = open(ctx({ eurUsd: null, available: M(100, "USD") }), {}, { change: true });
    expect(await screen.findByRole("dialog", { name: "Cambiar el saldo de Flor y Encanto" })).toBeTruthy();
    await user.click(screen.getByRole("radio", { name: "Devolver a tu cuenta" }));
    const field = screen.getByRole("textbox", { name: "Cuánto devuelves, en USD" });
    await user.type(field, "20");
    expect(screen.getByText("Solo puedes devolver hasta 15,50 USD, lo que le queda.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Devolver a tu cuenta" })).toBeDisabled();
    await user.clear(field);
    await user.type(field, "5");
    await user.click(screen.getByRole("button", { name: "Devolver a tu cuenta" }));
    await waitFor(() => expect(actions.lower).toHaveBeenCalledWith(expect.objectContaining({ ref: "flor-y-encanto", amount: M(5, "USD") })));
    expect(plain(toast.success.mock.calls[0]?.[0] as string)).toBe("Devueltos 5,00 USD a tu cuenta. A Flor y Encanto le quedan 10,50 USD.");
  });
});
