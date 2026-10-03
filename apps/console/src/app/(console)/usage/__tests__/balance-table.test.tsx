import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const save = vi.fn<(a: unknown) => Promise<{ ok: true; data: object }>>(async () => ({ ok: true as const, data: {} }));
const move = vi.fn<(a: unknown) => Promise<{ ok: true; data: object }>>(async () => ({ ok: true as const, data: {} }));
vi.mock("../actions", () => ({ saveAllocationAction: (a: unknown) => save(a), moveAllocationAction: (a: unknown) => move(a) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const { BalanceTable } = await import("../balance-table");

const rows = [
  { ref: "flor", name: "Flor y Encanto", capCents: 4_000, remainingCents: 880, monthCents: 3_120 },
  { ref: "lola", name: "Lola Mento", capCents: 0, remainingCents: 0, monthCents: 0 },
];
const everyone = [
  { ref: "flor", name: "Flor y Encanto" },
  { ref: "lola", name: "Lola Mento" },
  { ref: "nuevo", name: "Nuevo" },
];

function pintar(canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <BalanceTable rows={rows} unassigned={[{ ref: "nuevo", name: "Nuevo" }]} everyone={everyone} canWrite={canWrite} exhausted={false} />
    </LocaleProvider>,
  );
}
const plain = (s: string | null | undefined) => (s ?? "").replace(/ /g, " ");

describe("Saldo por cliente (spec 028)", () => {
  it("each row says cap, spent this month and what is left, in dollars, with no field to edit", () => {
    pintar();
    const flor = screen.getByRole("link", { name: "Flor y Encanto" }).closest("tr")!;
    expect(plain(flor.textContent)).toContain("40,00 US$");
    expect(plain(flor.textContent)).toContain("31,20 US$");
    expect(plain(flor.textContent)).toContain("8,80 US$");
    expect(screen.queryByRole("textbox")).toBeNull();
    const lola = screen.getByRole("link", { name: "Lola Mento" }).closest("tr")!;
    expect(within(lola).getByText("Sin saldo")).toBeTruthy();
  });

  it("changing the cap is «⋯», «Cambiar tope», save — in dollars, sent as cents", async () => {
    const user = userEvent.setup();
    pintar();
    await user.click(screen.getByRole("button", { name: "Opciones de Flor y Encanto" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cambiar tope" }));
    const field = await screen.findByLabelText("Importe en dólares");
    expect((field as HTMLInputElement).value).toBe("40,00");
    await user.clear(field);
    await user.type(field, "55,5");
    await user.click(screen.getByRole("button", { name: "Guardar tope" }));
    expect(save).toHaveBeenCalledWith({ client_ref: "flor", cap_cents: 5_550 });
  });

  it("moving balance names the source, caps the amount and sends cents", async () => {
    const user = userEvent.setup();
    pintar();
    await user.click(screen.getByRole("button", { name: "Opciones de Flor y Encanto" }));
    await user.click(await screen.findByRole("menuitem", { name: "Mover saldo a otro cliente" }));
    expect(await screen.findByText("Mover saldo desde Flor y Encanto")).toBeTruthy();
    expect(plain(screen.getByText(/Puedes mover hasta/).textContent)).toBe("Puedes mover hasta 40,00 US$.");
    await user.type(screen.getByLabelText("Importe a mover"), "50");
    await user.click(screen.getByRole("button", { name: "Mover saldo" }));
    expect(move).not.toHaveBeenCalled();
    expect(plain(screen.getByRole("alert").textContent)).toContain("solo tiene 40,00 US$ de tope");
    await user.clear(screen.getByLabelText("Importe a mover"));
    await user.type(screen.getByLabelText("Importe a mover"), "10");
    await user.click(screen.getByRole("button", { name: "Mover saldo" }));
    expect(move).toHaveBeenCalledWith({ from_ref: "flor", to_ref: "lola", amount_cents: 1_000 });
  });

  it("who only reads gets the view options, not the ones that change money", async () => {
    const user = userEvent.setup();
    pintar(false);
    expect(screen.queryByRole("button", { name: "Asignar saldo a un cliente" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Opciones de Flor y Encanto" }));
    expect(await screen.findByRole("menuitem", { name: "Ver su gasto" })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: "Cambiar tope" })).toBeNull();
  });
});
