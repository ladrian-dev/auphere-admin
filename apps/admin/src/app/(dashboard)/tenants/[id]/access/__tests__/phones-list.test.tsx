import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClientMemberOut, ClientPhoneOut } from "@/lib/backend";

const h = vi.hoisted(() => ({ list: vi.fn(), close: vi.fn(), success: vi.fn() }));
vi.mock("../actions", () => ({
  listPhonesAction: (...a: unknown[]) => h.list(...a),
  closePhoneAction: (...a: unknown[]) => h.close(...a),
  setAccessAction: vi.fn(),
  inviteAction: vi.fn(),
  resendAction: vi.fn(),
  revokeAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const { MembersList } = await import("../members-list");

const member: ClientMemberOut = {
  id: "m1",
  kind: "member",
  email: "valeria@flor.test",
  name: "Valeria",
  status: "active",
  since: "2026-10-01T00:00:00Z",
  expires_at: null,
};
const phone = (o: Partial<ClientPhoneOut> = {}): ClientPhoneOut => ({
  id: "p1",
  display_name: "iPhone de Valeria",
  platform: "ios",
  app_version: "1.0.0",
  last_seen_at: new Date().toISOString(),
  enrolled_at: "2026-10-02T09:00:00Z",
  revoked_at: null,
  revoked_reason: null,
  revoked_by: null,
  ...o,
});

async function openPhones() {
  render(<MembersList tenantId="t1" members={[member]} />);
  await userEvent.click(screen.getByRole("button", { name: "Teléfonos de valeria@flor.test" }));
  return screen.findByRole("dialog");
}

/** Spec 031 (R7.4): a person's phones in the operator's access tab. */
describe("PhonesDialog", () => {
  beforeEach(() => {
    h.list.mockReset();
    h.close.mockReset();
    h.success.mockReset();
  });

  it("lists the signed-in phones first and the closed ones with why", async () => {
    h.list.mockResolvedValue({
      ok: true,
      data: [
        phone(),
        phone({
          id: "p2",
          display_name: "Pixel 9",
          platform: "android",
          revoked_at: "2026-10-10T00:00:00Z",
          revoked_reason: "closed_by_auphere",
          revoked_by: "operator:ana@auphere.com",
        }),
      ],
    });
    const dialog = await openPhones();
    const list = await within(dialog).findByRole("list", { name: "Teléfonos de valeria@flor.test" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(dialog).getByText("Con sesión")).toBeTruthy();
    expect(within(dialog).getByText(/Lo cerró Auphere · ana@auphere\.com/)).toBeTruthy();
    // Only a signed-in phone can be closed.
    expect(within(dialog).getAllByRole("button", { name: /Cerrar el teléfono/ })).toHaveLength(1);
    expect(h.list).toHaveBeenCalledWith("t1", "m1");
  });

  it("asks in the row before closing, and nothing happens on cancel", async () => {
    h.list.mockResolvedValue({ ok: true, data: [phone()] });
    const dialog = await openPhones();
    await userEvent.click(await within(dialog).findByRole("button", { name: "Cerrar el teléfono «iPhone de Valeria»" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(h.close).not.toHaveBeenCalled();
  });

  it("closes the phone after the confirmation and reads the list again", async () => {
    h.list
      .mockResolvedValueOnce({ ok: true, data: [phone()] })
      .mockResolvedValueOnce({ ok: true, data: [phone({ revoked_at: new Date().toISOString(), revoked_reason: "closed_by_auphere" })] });
    h.close.mockResolvedValue({ ok: true, data: null });
    const dialog = await openPhones();
    await userEvent.click(await within(dialog).findByRole("button", { name: "Cerrar el teléfono «iPhone de Valeria»" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Sí, cerrar teléfono" }));
    expect(h.close).toHaveBeenCalledWith("t1", "m1", "p1");
    await waitFor(() => expect(within(dialog).getByText("Cerrado")).toBeTruthy());
    expect(h.success).toHaveBeenCalled();
  });

  it("partial: a close that fails says so and keeps the list", async () => {
    h.list.mockResolvedValue({ ok: true, data: [phone()] });
    h.close.mockResolvedValue({ ok: false, error: "Error 503" });
    const dialog = await openPhones();
    await userEvent.click(await within(dialog).findByRole("button", { name: "Cerrar el teléfono «iPhone de Valeria»" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Sí, cerrar teléfono" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("No se pudo cerrar «iPhone de Valeria»");
    expect(within(dialog).getByText("iPhone de Valeria")).toBeTruthy();
  });

  it("empty: says the person has not signed in from a phone", async () => {
    h.list.mockResolvedValue({ ok: true, data: [] });
    const dialog = await openPhones();
    expect((await within(dialog).findByRole("status")).textContent).toContain("No ha entrado desde ningún teléfono");
  });

  it("error: a failed read offers a retry, never an empty list", async () => {
    h.list.mockResolvedValueOnce({ ok: false, error: "Error 500" }).mockResolvedValueOnce({ ok: true, data: [phone()] });
    const dialog = await openPhones();
    expect((await within(dialog).findByRole("alert")).textContent).toContain("No se pudieron leer los teléfonos");
    expect(within(dialog).queryByText("No ha entrado desde ningún teléfono")).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Reintentar" }));
    expect(await within(dialog).findByText("iPhone de Valeria")).toBeTruthy();
  });

  it("an invitation has no phones button", () => {
    render(<MembersList tenantId="t1" members={[{ ...member, kind: "invitation", status: "pending" }]} />);
    expect(screen.queryByRole("button", { name: /Teléfonos de/ })).toBeNull();
  });
});
