/**
 * Spec 005 · R3 — comprar crédito desde la consola.
 *
 * El formulario **no acredita nada**: abre la página del proveedor. Lo que se
 * prueba aquí son las dos cosas que sí decide la pantalla:
 *
 * 1. **Los importes imposibles se paran antes de salir.** Un cero de más
 *    tecleado es el error más caro que alguien puede cometer en esta
 *    pantalla, y la API lo rechazaría — pero rebotar contra un 422 es una
 *    forma peor de enterarse que un mensaje en el sitio.
 * 2. **Se dice cuánto saldo compra ese dinero**, antes de pagar. Sin eso,
 *    «50 $» no significa nada: la relación con lo que consume un turno es
 *    justo lo que el partner no tiene por qué saber de memoria.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const buyCredit = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/billing/actions", () => ({
  buyCreditAction: (...args: unknown[]) => buyCredit(...args),
  startCheckoutAction: vi.fn(),
  openPortalAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";

import { BuyCreditForm } from "../buy-credit-form";

function form() {
  return render(
    <LocaleProvider locale="es">
      <BuyCreditForm />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  buyCredit.mockReset();
  buyCredit.mockResolvedValue({ ok: true, data: { url: "https://pago.example/x", applied: false } });
});

describe("los importes imposibles no salen de la pantalla", () => {
  it("no envía nada por debajo del mínimo", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText(/importe|cantidad/i));
    await user.type(screen.getByLabelText(/importe|cantidad/i), "1");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("no envía un cero de más", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText(/importe|cantidad/i));
    await user.type(screen.getByLabelText(/importe|cantidad/i), "500000");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("no envía texto", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText(/importe|cantidad/i));
    await user.type(screen.getByLabelText(/importe|cantidad/i), "mucho");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("un importe válido sí sale, en centavos", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText(/importe|cantidad/i));
    await user.type(screen.getByLabelText(/importe|cantidad/i), "50");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).toHaveBeenCalledWith({ amount_cents: 5000 });
  });
});

describe("se dice qué compra ese dinero", () => {
  it("muestra las unidades equivalentes al importe escrito", async () => {
    const user = userEvent.setup();
    const { container } = form();
    await user.clear(screen.getByLabelText(/importe|cantidad/i));
    await user.type(screen.getByLabelText(/importe|cantidad/i), "50");
    // 50 USD a 10 USD por millón = 5 millones de unidades.
    expect(container.textContent?.replace(/[.\s ]/g, "")).toContain("5000000");
  });

  it("con el campo vacío no promete nada", () => {
    const { container } = form();
    expect(container.textContent).not.toContain("000000");
  });
});
