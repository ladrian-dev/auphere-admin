import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DRIFT, POLICY, WHISPER, row, today, yesterday } from "./fixtures";

const h = vi.hoisted(() => ({ price: vi.fn(), weights: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: (...a: unknown[]) => h.price(...a),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: (...a: unknown[]) => h.weights(...a),
  putSalePolicyAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { PriceDialog } = await import("../deployment-dialogs");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

async function openFor(r = row(), policy = POLICY) {
  render(<PriceDialog row={r} policy={policy} />);
  await userEvent.click(screen.getByRole("button", { name: `Precio de ${r.display_name}` }));
  return screen.findByRole("dialog");
}

const field = (dialog: HTMLElement, name: RegExp) => within(dialog).getByRole("textbox", { name }) as HTMLInputElement;
const date = (dialog: HTMLElement) => dialog.querySelector('input[type="date"]') as HTMLInputElement;

async function retype(input: HTMLInputElement, value: string) {
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

/** Spec 059, historia 4 and 3.9: a cost dialog that says what there is. */
describe("the cost dialog", () => {
  it("starts from the cost in force and today (4.3)", async () => {
    const dialog = await openFor();
    expect(within(dialog).getByRole("heading", { name: "Coste de Terra" })).toBeTruthy();
    expect(field(dialog, /^Entrada/).value).toBe("4");
    expect(field(dialog, /^Lectura de caché/).value).toBe("0,4");
    expect(field(dialog, /^Salida/).value).toBe("20");
    expect(field(dialog, /^Fuente/).value).toBe("https://openai.com/api/pricing/");
    expect(date(dialog).value).toBe(today());
  });

  it("says, before saving, that the cost moves the margin and not what the partner pays (4.5)", async () => {
    const dialog = await openFor();
    expect(dialog.textContent).toMatch(/solo mueve el margen de Auphere/);
    expect(dialog.textContent).toMatch(/lo que paga el partner/);
  });

  it("shows the multiplier of each lane with the new cost and the current weights (4.5)", async () => {
    const dialog = await openFor();
    const preview = within(dialog).getByRole("group", { name: "Multiplicador con el coste nuevo" });
    expect(preview.textContent).toContain("2,2×");
    await retype(field(dialog, /^Salida/), "25");
    expect(preview.textContent).toContain("1,76×");
    expect(preview.textContent).toMatch(/desfasada/);
    await retype(field(dialog, /^Salida/), "40");
    expect(preview.textContent).toMatch(/bajo el suelo/i);
  });

  it("refuses a date before today, with its reason (4.4)", async () => {
    const dialog = await openFor();
    await retype(date(dialog), yesterday());
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el coste" }));
    expect(h.price).not.toHaveBeenCalled();
    expect(dialog.textContent).toMatch(/antes de hoy/);
  });

  it("saves the cost alone, without touching the weights", async () => {
    h.price.mockResolvedValue({ ok: true, data: { deployment: row() } });
    const dialog = await openFor();
    await retype(field(dialog, /^Entrada/), "4,2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el coste" }));
    expect(h.price).toHaveBeenCalledTimes(1);
    const [uuid, body] = h.price.mock.calls[0] as [string, Record<string, unknown>];
    expect(uuid).toBe("d1");
    expect(body).toMatchObject({ valid_from: today(), input: 4.2, cache_read: 0.4, output: 20, currency: "USD" });
    expect(h.weights).not.toHaveBeenCalled();
    expect(h.refresh).toHaveBeenCalled();
  });

  it("offers «Aplicar la propuesta de venta» when the new cost leaves the sale behind (3.9)", async () => {
    h.price.mockResolvedValue({ ok: true, data: { deployment: DRIFT } });
    h.weights.mockResolvedValue({ ok: true, data: DRIFT });
    const dialog = await openFor();
    expect(within(dialog).queryByRole("checkbox", { name: "Aplicar la propuesta de venta" })).toBeNull();
    await retype(field(dialog, /^Salida/), "25");
    const apply = within(dialog).getByRole("checkbox", { name: "Aplicar la propuesta de venta" });
    await userEvent.click(apply);
    expect(dialog.textContent).toContain("5,5");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el coste" }));
    expect(h.price).not.toHaveBeenCalled();
    expect(dialog.textContent).toContain("Hace falta el motivo");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Subió la salida");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el coste" }));
    expect(h.price).toHaveBeenCalledTimes(1);
    expect(h.weights).toHaveBeenCalledWith("d1", {
      input: "0.88",
      cache_read: "0.088",
      output: "5.5",
      reason: "Subió la salida",
    });
  });

  it("a cost for a later day does not offer the proposal yet", async () => {
    const dialog = await openFor();
    await retype(field(dialog, /^Salida/), "25");
    await retype(date(dialog), "2099-01-01");
    expect(within(dialog).queryByRole("checkbox", { name: "Aplicar la propuesta de venta" })).toBeNull();
    expect(dialog.textContent).toMatch(/el día que entre en vigor/);
  });

  it("without the target multiplier, shows the multipliers but proposes nothing (4.7)", async () => {
    const dialog = await openFor(row(), { ...POLICY, multiplier: null });
    await retype(field(dialog, /^Salida/), "25");
    expect(within(dialog).getByRole("group", { name: "Multiplicador con el coste nuevo" }).textContent).toContain("1,76×");
    expect(within(dialog).queryByRole("checkbox", { name: "Aplicar la propuesta de venta" })).toBeNull();
  });

  it("a model priced by the minute has no lanes to preview", async () => {
    const dialog = await openFor(WHISPER);
    expect(within(dialog).queryByRole("group", { name: "Multiplicador con el coste nuevo" })).toBeNull();
    expect(dialog.textContent).toMatch(/por minuto/);
    expect(field(dialog, /^Minuto de audio/).value).toBe("0,006");
  });
});
