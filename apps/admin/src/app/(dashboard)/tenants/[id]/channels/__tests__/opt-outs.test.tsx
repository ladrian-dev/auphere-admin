import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OptOut } from "@/lib/backend";

import { OptOuts } from "../opt-outs";

const lift = vi.fn();
vi.mock("../actions", () => ({
  liftOptOutAction: (...args: unknown[]) => lift(...args),
}));
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: vi.fn() } }));

const row = (over: Partial<OptOut>): OptOut => ({
  id: "o1",
  channel_id: "c1",
  channel_identifier: "+34600000001",
  customer_id: null,
  customer_name: "Ana",
  phone: "34611000001",
  scope: "marketing",
  source: "keyword",
  reason: "keyword_stop",
  opted_out_at: "2026-10-29T10:00:00Z",
  opted_in_at: null,
  lifted_by: null,
  liftable: true,
  ...over,
});

describe("las bajas de WhatsApp en el panel (spec 050, 5.5)", () => {
  beforeEach(() => {
    lift.mockReset();
    toastError.mockReset();
  });

  it("dice cuántas personas no reciben marketing y que el agente les sigue respondiendo", () => {
    render(<OptOuts tenantId="t1" rows={[row({}), row({ id: "o2", source: "meta", liftable: false, customer_name: "Luis" })]} />);
    expect(screen.getByText(/2 personas no reciben difusiones ni plantillas de marketing/)).toBeInTheDocument();
    expect(screen.getByText("Solo la persona")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Levantar" })).toHaveLength(1);
  });

  it("levantar pide un motivo y lo manda", async () => {
    lift.mockResolvedValue({ ok: true, data: null });
    const user = userEvent.setup();
    render(<OptOuts tenantId="t1" rows={[row({})]} />);
    await user.click(screen.getByRole("button", { name: "Levantar" }));
    const confirm = screen.getByRole("button", { name: "Levantar la baja" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Motivo"), "Lo pidió por teléfono");
    await user.click(confirm);
    expect(lift).toHaveBeenCalledWith("t1", "o1", "Lo pidió por teléfono");
  });

  it("una baja de Meta rechazada lo explica", async () => {
    lift.mockResolvedValue({ ok: false, error: "lifted_by_person_only" });
    const user = userEvent.setup();
    render(<OptOuts tenantId="t1" rows={[row({})]} />);
    await user.click(screen.getByRole("button", { name: "Levantar" }));
    await user.type(screen.getByLabelText("Motivo"), "Motivo largo");
    await user.click(screen.getByRole("button", { name: "Levantar la baja" }));
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining("solo ella puede reactivarla"));
  });
});
