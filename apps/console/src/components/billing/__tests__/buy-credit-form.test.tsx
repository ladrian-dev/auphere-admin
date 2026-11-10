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
    await user.clear(screen.getByLabelText("Otro importe"));
    await user.type(screen.getByLabelText("Otro importe"), "1");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("no envía un cero de más", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText("Otro importe"));
    await user.type(screen.getByLabelText("Otro importe"), "500000");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("no envía texto", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText("Otro importe"));
    await user.type(screen.getByLabelText("Otro importe"), "mucho");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).not.toHaveBeenCalled();
  });

  it("un importe válido sí sale, en centavos", async () => {
    const user = userEvent.setup();
    form();
    await user.clear(screen.getByLabelText("Otro importe"));
    await user.type(screen.getByLabelText("Otro importe"), "50");
    await user.click(screen.getByRole("button", { name: /comprar/i }));
    expect(buyCredit).toHaveBeenCalledWith({ amount_cents: 5000 });
  });
});

describe("las cantidades rápidas del prototipo (20 · 50 · 100 · 250)", () => {
  it("un clic elige el importe, lo marca y se compra con «Comprar»", async () => {
    const user = userEvent.setup();
    form();
    const quick = screen.getByRole("group", { name: "Importes rápidos" });
    const buttons = Array.from(quick.querySelectorAll("button")).map((b) => b.textContent?.replace(/\u00a0/g, " "));
    expect(buttons).toEqual(["20,00 US$", "50,00 US$", "100,00 US$", "250,00 US$"]);
    await user.click(screen.getByRole("button", { name: /^100,00\sUS\$$/ }));
    expect(screen.getByRole("button", { name: /^100,00\sUS\$$/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Otro importe")).toHaveValue(null);
    await user.click(screen.getByRole("button", { name: "Comprar" }));
    expect(buyCredit).toHaveBeenCalledWith({ amount_cents: 10000 });
  });

  it("«Comprar» está apagado sin importe válido y el rango se dice sin «dólares» escrito a mano", async () => {
    const user = userEvent.setup();
    const { container } = form();
    expect(screen.getByRole("button", { name: "Comprar" })).toBeDisabled();
    const hint = screen.getByText("Entre 5 y 5000, en números enteros.");
    expect(container.textContent).not.toMatch(/dólares/);
    expect(hint.textContent).not.toMatch(/US\$/);
    await user.type(screen.getByLabelText("Otro importe"), "3");
    expect(screen.getByText("El importe tiene que estar entre 5 y 5000, en números enteros.")).toBeInTheDocument();
  });

  it("si la cuenta va en otra moneda, dice en cuál se cobra", () => {
    render(
      <LocaleProvider locale="es">
        <BuyCreditForm accountCurrency="EUR" />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Se cobra en USD en la página segura del proveedor/)).toBeInTheDocument();
  });
});

describe("se dice qué compra ese dinero (spec 027: dinero, no unidades)", () => {
  it("lo que paga es lo que recibe de saldo", async () => {
    const user = userEvent.setup();
    const { container } = form();
    await user.clear(screen.getByLabelText("Otro importe"));
    await user.type(screen.getByLabelText("Otro importe"), "50");
    expect(container.textContent?.replace(/\u00a0/g, " ")).toContain("Recibirás 50,00 US$ de saldo.");
    expect(container.textContent).not.toMatch(/unidades|créditos/);
  });

  it("con el campo vacío no promete nada", () => {
    const { container } = form();
    expect(container.textContent).not.toContain("Recibirás");
  });
});
