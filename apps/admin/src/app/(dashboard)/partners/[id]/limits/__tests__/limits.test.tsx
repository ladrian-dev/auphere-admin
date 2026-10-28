import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BuildBudget } from "@/lib/backend-levers";

const h = vi.hoisted(() => ({ budget: vi.fn(), currency: vi.fn(), success: vi.fn(), info: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  setBuildBudgetAction: (...a: unknown[]) => h.budget(...a),
  setAccountCurrencyAction: (...a: unknown[]) => h.currency(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, info: h.info, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { BuildBudgetForm } = await import("../build-budget-form");
const { AccountCurrencyForm } = await import("../account-currency-form");
const { BudgetRequests } = await import("../budget-requests");
const { BUDGET_ERRORS, budgetSummary, checkBudget, currencyConfirmText, currencyResultText, monthLabel, otherCurrency } =
  await import("../limits");

const PARTNER = "pppppppp-0000-0000-0000-000000000001";

const USD_BUDGET: BuildBudget = {
  currency: "USD",
  month: "2026-10-01",
  cap: { amount_micros: 5_000_000, currency: "USD" },
  spent: { amount_micros: 1_230_000, currency: "USD" },
  state: "ok",
};
const EUR_BUDGET: BuildBudget = {
  currency: "EUR",
  month: "2026-10-01",
  cap: { amount_micros: 4_000_000, currency: "EUR" },
  spent: { amount_micros: 4_000_000, currency: "EUR" },
  state: "exhausted",
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T172; 43.1, 46.5, 54.5): the cap of «Construcción y pruebas» and the account currency. */
describe("the rules of the cap and the currency", () => {
  it("takes the cap in money, with its reason", () => {
    expect(checkBudget({ amount: "", currency: "USD", reason: "" })).toEqual({
      ok: false,
      errors: { amount: "Escribe el tope.", reason: "Hace falta el motivo." },
    });
    expect(checkBudget({ amount: "50 tokens", currency: "USD", reason: "Lanzamiento" })).toMatchObject({
      ok: false,
      errors: { amount: expect.stringMatching(/dos decimales/) },
    });
    expect(checkBudget({ amount: "49,90", currency: "EUR", reason: " Lanzamiento " })).toEqual({
      ok: true,
      cap: { amount_micros: 4_990_000, currency: "EUR" },
      reason: "Lanzamiento",
    });
    expect(checkBudget({ amount: "0", currency: "USD", reason: "Pausa" })).toMatchObject({ ok: true, cap: { amount_micros: 0 } });
  });

  it("says this month's spend against the cap, and the only other currency", () => {
    expect(budgetSummary(USD_BUDGET)).toMatch(/^Octubre de 2026: gastado 12,30\sUSD de 50,00\sUSD\.$/);
    expect(otherCurrency("USD")).toBe("EUR");
    expect(otherCurrency("EUR")).toBe("USD");
  });

  it("names the month and what the currency change did", () => {
    expect(monthLabel("2026-10-01")).toBe("octubre de 2026");
    expect(currencyConfirmText("EUR")).toMatch(/Se convierte el saldo que le queda/);
    expect(currencyConfirmText("EUR")).toMatch(/cambio del BCE/);
    expect(currencyResultText({ currency: "USD", changed: false })).toBe("La cuenta ya estaba en USD: no se convirtió nada.");
    const changed = currencyResultText({
      currency: "EUR",
      changed: true,
      from: "USD",
      fx: { rate: "0.9214", date: "2026-10-28", source: "ECB" },
      purchased_micros: 9_214_000,
    });
    expect(changed).toMatch(/^Cuenta convertida de USD a EUR a 0,9214 \(BCE del 2026-10-28\)\./);
    expect(changed).toMatch(/Saldo comprado que queda: 92,14\s€\./);
  });
});

describe("the cap form", () => {
  it("starts from this month's cap, in the account's currency, with its state", () => {
    render(<BuildBudgetForm partnerId={PARTNER} budget={EUR_BUDGET} />);
    expect((screen.getByRole("textbox", { name: /Tope mensual \(EUR\)/ }) as HTMLInputElement).value).toBe("40,00");
    expect(screen.getByText("Agotada")).toBeTruthy();
    expect(screen.getByText(/gastado 40,00\s€ de 40,00\s€/)).toBeTruthy();
    // The operator does not pick the currency: the account's is the only one.
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("does not save without an amount and a reason, and saves in the account's currency", async () => {
    h.budget.mockResolvedValue({ ok: true, data: { cap: { amount_micros: 4_990_000, currency: "USD" }, month: "2026-10-01" } });
    render(<BuildBudgetForm partnerId={PARTNER} budget={USD_BUDGET} />);
    const amount = screen.getByRole("textbox", { name: /Tope mensual/ });
    await userEvent.clear(amount);
    const save = screen.getByRole("button", { name: "Guardar el tope" });
    await userEvent.click(save);
    expect(h.budget).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe el tope.")).toBeTruthy();
    expect(screen.getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.type(amount, "49,90");
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Lanzamiento de noviembre");
    await userEvent.click(save);
    expect(h.budget).toHaveBeenCalledWith(PARTNER, {
      cap: { amount_micros: 4_990_000, currency: "USD" },
      reason: "Lanzamiento de noviembre",
    });
    expect(screen.getByRole("status").textContent).toMatch(/Tope de octubre de 2026 y de los meses que vienen: 49,90\sUSD\./);
    expect(h.refresh).toHaveBeenCalled();
  });

  it("speaks of money, never of tokens", () => {
    const { container } = render(<BuildBudgetForm partnerId={PARTNER} budget={USD_BUDGET} />);
    expect(container.textContent?.toLowerCase()).not.toContain("token");
  });

  it("says the API's refusal in words", async () => {
    h.budget.mockResolvedValue({ ok: false, code: "currency_mismatch", error: BUDGET_ERRORS.currency_mismatch });
    render(<BuildBudgetForm partnerId={PARTNER} budget={EUR_BUDGET} />);
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Ampliación");
    await userEvent.click(screen.getByRole("button", { name: "Guardar el tope" }));
    expect(h.budget).toHaveBeenCalledWith(PARTNER, { cap: { amount_micros: 4_000_000, currency: "EUR" }, reason: "Ampliación" });
    expect(screen.getByRole("alert").textContent).toContain("La moneda de la cuenta acaba de cambiar");
    expect(h.refresh).not.toHaveBeenCalled();
  });
});

describe("the «Pedir ampliación» list", () => {
  it("lists who asked and when, the newest first as the API sends them", () => {
    render(
      <BudgetRequests
        requests={[
          { requested_by: "console:maria@facelad.com", created_at: "2026-10-27T09:00:00Z" },
          { requested_by: "companion:12345678-0000-0000-0000-000000000000", created_at: "2026-10-26T09:00:00Z" },
        ]}
      />,
    );
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("maria@facelad.com")).toBeTruthy();
    expect(within(rows[2]!).getByText("Companion (12345678)")).toBeTruthy();
  });

  it("says when nobody asked", () => {
    render(<BudgetRequests requests={[]} />);
    expect(screen.getByText("Nadie ha pedido ampliación")).toBeTruthy();
  });
});

describe("the account currency", () => {
  it("only offers the other currency, asks for a reason, says it converts the balance, and changes it on confirmation", async () => {
    h.currency.mockResolvedValue({
      ok: true,
      data: { currency: "EUR", changed: true, from: "USD", fx: { rate: "0.92", date: "2026-10-28", source: "ECB" }, purchased_micros: 9_200_000 },
    });
    render(<AccountCurrencyForm partnerId={PARTNER} partnerName="Demo Auditoría" current="USD" />);
    expect(screen.getByText(/La cuenta está en dólares \(USD\)\. Solo puede pasar a euros \(EUR\)\./)).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    const change = screen.getByRole("button", { name: "Cambiar a EUR…" });
    await userEvent.click(change);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "El partner factura en euros");
    await userEvent.click(change);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Se convierte el saldo que le queda/)).toBeTruthy();
    expect(h.currency).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Convertir y cambiar" }));
    expect(h.currency).toHaveBeenCalledWith(PARTNER, { currency: "EUR", reason: "El partner factura en euros" });
    expect(screen.getByRole("status").textContent).toMatch(/Cuenta convertida de USD a EUR/);
    expect(h.success).toHaveBeenCalledWith("La cuenta de Demo Auditoría ya está en EUR", expect.anything());
  });

  it("lets the operator pick when the current currency could not be read", async () => {
    h.currency.mockResolvedValue({ ok: true, data: { currency: "USD", changed: false } });
    render(<AccountCurrencyForm partnerId={PARTNER} partnerName="Demo Auditoría" current={null} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Nueva moneda/ }), "USD");
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Comprobación");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar la moneda…" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Convertir y cambiar" }));
    expect(h.currency).toHaveBeenCalledWith(PARTNER, { currency: "USD", reason: "Comprobación" });
    expect(screen.getByRole("status").textContent).toBe("La cuenta ya estaba en USD: no se convirtió nada.");
  });

  it("keeps the dialog open with the API's refusal", async () => {
    h.currency.mockResolvedValue({ ok: false, code: "fx_unavailable", error: "No hay cambio del BCE para hoy. Vuelve a intentarlo más tarde." });
    render(<AccountCurrencyForm partnerId={PARTNER} partnerName="Demo Auditoría" current="USD" />);
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Factura en euros");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar a EUR…" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Convertir y cambiar" }));
    expect(within(dialog).getByRole("alert").textContent).toContain("No hay cambio del BCE");
    expect(h.refresh).not.toHaveBeenCalled();
  });
});
