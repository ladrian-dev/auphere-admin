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

/** Un nombre accesible con importes: los formateadores separan con un espacio duro. */
const named = (text: string) => new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s")}$`);

describe("las cantidades rápidas del prototipo (20 · 50 · 100 · 250)", () => {
  it("un clic elige el importe, lo marca con un tinte y el botón dice cuánto compra (072 §6.1)", async () => {
    const user = userEvent.setup();
    form();
    const quick = screen.getByRole("radiogroup", { name: "Importes rápidos" });
    const options = Array.from(quick.querySelectorAll("label")).map((l) => l.textContent?.replace(/\u00a0/g, " "));
    expect(options).toEqual(["20,00 USD", "50,00 USD", "100,00 USD", "250,00 USD"]);
    const hundred = screen.getByRole("radio", { name: named("100,00 USD") });
    await user.click(hundred);
    // Un clic elige, no compra: el importe queda marcado y nada sale aún.
    expect(hundred).toBeChecked();
    expect(buyCredit).not.toHaveBeenCalled();
    const label = hundred.closest("label")!;
    expect(label).toHaveAttribute("data-checked", "true");
    expect(label.className).toMatch(/(^|\s)bg-primary\/10(\s|$)/);
    expect(label.className).not.toMatch(/(^|\s)bg-primary(\s|$)/);
    expect(screen.getByRole("radio", { name: named("50,00 USD") })).not.toBeChecked();
    // El campo libre sigue ahí, vacío.
    expect(screen.getByLabelText("Otro importe")).toHaveValue(null);
    await user.click(screen.getByRole("button", { name: named("Comprar 100,00 USD") }));
    expect(buyCredit).toHaveBeenCalledWith({ amount_cents: 10000 });
  });

  it("escribir otro importe quita la marca del rápido y el botón dice el nuevo", async () => {
    const user = userEvent.setup();
    form();
    await user.click(screen.getByRole("radio", { name: named("50,00 USD") }));
    await user.type(screen.getByLabelText("Otro importe"), "75");
    expect(screen.getByRole("radio", { name: named("50,00 USD") })).not.toBeChecked();
    expect(screen.getByRole("button", { name: named("Comprar 75,00 USD") })).toBeEnabled();
  });

  it("«Comprar» está apagado sin importe válido y el rango se dice sin «dólares» escrito a mano", async () => {
    const user = userEvent.setup();
    const { container } = form();
    const buy = screen.getByRole("button", { name: "Comprar" });
    expect(buy).toBeDisabled();
    const hint = screen.getByText("Entre 5 y 5000, en números enteros.");
    // Sin importe, el botón dice por qué está apagado (072 §6.2).
    expect(buy).toHaveAccessibleDescription("Entre 5 y 5000, en números enteros.");
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
    expect(container.textContent?.replace(/\u00a0/g, " ")).toContain("Recibirás 50,00 USD de saldo.");
    expect(container.textContent).not.toMatch(/unidades|créditos/);
  });

  it("con el campo vacío no promete nada", () => {
    const { container } = form();
    expect(container.textContent).not.toContain("Recibirás");
  });
});
