import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { MICROS_PER_UNIT, Money, formatMoney, moneyFromMicros } from "../money";

/**
 * Spec 047 (R45.9): los importes van en `es-ES`, con dos decimales, separador
 * de miles siempre y el símbolo detrás («1.234,50 €», «60,00 USD»), en números
 * tabulares. Solo hay euros y dólares.
 */
const NB = " ";

describe("formatMoney", () => {
  it("euros: dos decimales, miles y el símbolo detrás", () => {
    expect(formatMoney(1234.5, "EUR")).toBe(`1.234,50${NB}€`);
    expect(formatMoney(240, "EUR")).toBe(`240,00${NB}€`);
    expect(formatMoney(0.5, "EUR")).toBe(`0,50${NB}€`);
  });

  it("dólares: el código detrás, no «US$»", () => {
    expect(formatMoney(60, "USD")).toBe(`60,00${NB}USD`);
    expect(formatMoney(12345.678, "USD")).toBe(`12.345,68${NB}USD`);
  });

  it("el separador de miles va siempre, también con cuatro cifras (es-ES no lo pone solo)", () => {
    expect(formatMoney(1000, "EUR")).toBe(`1.000,00${NB}€`);
  });

  it("negativos y vacíos", () => {
    expect(formatMoney(-12, "EUR")).toBe(`-12,00${NB}€`);
    expect(formatMoney(null, "EUR")).toBe("—");
    expect(formatMoney(Number.NaN, "USD")).toBe("—");
  });

  it("lee el dinero del contrato (`amount_micros`, cien milésimas de la moneda)", () => {
    expect(MICROS_PER_UNIT).toBe(100_000);
    expect(moneyFromMicros({ amount_micros: 123_450_000, currency: "EUR" })).toEqual({ amount: 1234.5, currency: "EUR" });
  });
});

describe("<Money>", () => {
  it("pinta el importe en números tabulares y sin partirse", async () => {
    render(
      <p>
        Saldo: <Money amount={1234.5} currency="EUR" />
      </p>,
    );
    const money = screen.getByText("1.234,50 €");
    expect(money).toHaveAttribute("data-slot", "money");
    expect(money.className).toMatch(/\btabular-nums\b/);
    expect(money.className).toMatch(/\bwhitespace-nowrap\b/);
    expect(await axeViolations()).toEqual([]);
  });

  it("acepta el dinero tal como llega de la API", () => {
    render(<Money value={{ amount_micros: 6_000_000, currency: "USD" }} />);
    expect(screen.getByText("60,00 USD")).toBeInTheDocument();
  });

  it("sin importe dice «—»", () => {
    render(<Money amount={null} currency="EUR" />);
    expect(screen.getByText("—")).toHaveAttribute("data-slot", "money");
  });
});
