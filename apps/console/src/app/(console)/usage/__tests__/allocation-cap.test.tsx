import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const save = vi.fn(async () => ({ ok: true as const, data: { client_ref: "a", cap_cents: 2550, remaining_cents: 2550 } }));
vi.mock("../actions", () => ({ saveAllocationAction: (...a: unknown[]) => save(...(a as [])) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const { AllocationCapForm } = await import("../allocation-cap");

function pintar(capCents = 500) {
  return render(
    <LocaleProvider locale="es">
      <AllocationCapForm clientRef="a" capCents={capCents} />
    </LocaleProvider>,
  );
}

describe("Tope de un cliente en dólares (spec 027)", () => {
  it("shows the cap in dollars and no save button until it changes", () => {
    pintar(500);
    expect((screen.getByLabelText("Tope") as HTMLInputElement).value).toBe("5,00");
    expect(screen.queryByRole("button", { name: "Guardar tope" })).toBeNull();
  });

  it("sends what the partner typed as cents, comma or point", async () => {
    const user = userEvent.setup();
    pintar(500);
    const input = screen.getByLabelText("Tope");
    await user.clear(input);
    await user.type(input, "25,5");
    await user.click(screen.getByRole("button", { name: "Guardar tope" }));
    expect(save).toHaveBeenCalledWith({ client_ref: "a", cap_cents: 2550 });
  });

  it("refuses an amount with three decimals and sends nothing", async () => {
    const user = userEvent.setup();
    save.mockClear();
    pintar(500);
    const input = screen.getByLabelText("Tope");
    await user.clear(input);
    await user.type(input, "4,555");
    await user.click(screen.getByRole("button", { name: "Guardar tope" }));
    expect(save).not.toHaveBeenCalled();
  });
});
