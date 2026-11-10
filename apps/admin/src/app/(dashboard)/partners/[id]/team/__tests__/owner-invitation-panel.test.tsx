import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OwnerInvitationResult, PartnerOwnerState } from "@/lib/backend";

const invite = vi.fn();
const resend = vi.fn();
const revoke = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("../../../_invitation/actions", () => ({
  inviteOwnerAction: (...a: unknown[]) => invite(...a),
  resendOwnerInvitationAction: (...a: unknown[]) => resend(...a),
  revokeOwnerInvitationAction: (...a: unknown[]) => revoke(...a),
}));

import { OwnerInvitationPanel, type AuphereInvitationRow } from "../owner-invitation-panel";

const open: PartnerOwnerState = {
  has_active_owner: false,
  can_invite: true,
  can_resend: true,
  block: null,
  expired_email: null,
  expired_at: null,
  suggested_email: null,
};
const row: AuphereInvitationRow = {
  id: "i1",
  email: "duena@acme.test",
  expiresOn: "24 de noviembre de 2026",
  sentAgo: "hace 2 h",
};
const live: PartnerOwnerState = { ...open, can_invite: false };
const result: OwnerInvitationResult = {
  id: "i2",
  email: "duena@acme.test",
  role: "owner",
  status: "pending",
  expires_at: "2026-11-24T19:00:00Z",
  created_at: "2026-11-03T19:00:00Z",
  last_sent_at: "2026-11-03T19:00:01Z",
  email_sent: true,
  accept_url: "https://console.test/invite/tok-nuevo",
};

function panel(owner: PartnerOwnerState, invitations: AuphereInvitationRow[] = []) {
  return (
    <OwnerInvitationPanel
      partnerId="p1"
      partnerName="Acme"
      owner={owner}
      invitations={invitations}
      expiredOn={owner.expired_at ? "1 de noviembre de 2026" : null}
    />
  );
}

describe("OwnerInvitationPanel (spec 052)", () => {
  beforeEach(() => {
    invite.mockReset();
    resend.mockReset();
    revoke.mockReset();
    refresh.mockReset();
  });

  // ── R3: invitar ──────────────────────────────────────────────────────────

  it("offers the form with the contact written and editable, and sends nothing until pressed", async () => {
    render(panel({ ...open, suggested_email: "contacto@acme.test" }));
    const input = screen.getByLabelText("Correo del propietario") as HTMLInputElement;
    expect(input.value).toBe("contacto@acme.test");
    expect(input.disabled).toBe(false);
    expect(invite).not.toHaveBeenCalled();

    invite.mockResolvedValue({ ok: true, data: result });
    const user = userEvent.setup();
    await user.clear(input);
    await user.type(input, "otra@acme.test");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    await vi.waitFor(() => expect(invite).toHaveBeenCalledWith("p1", "otra@acme.test"));
    expect(await screen.findByText("Invitación enviada a duena@acme.test")).toBeTruthy();
    expect(screen.getByText("https://console.test/invite/tok-nuevo")).toBeTruthy();
  });

  it("refuses an address with no shape in the field", async () => {
    render(panel(open));
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Correo del propietario"), "nada");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText("Eso no tiene forma de correo.")).toBeTruthy();
    expect(invite).not.toHaveBeenCalled();
  });

  it("says in the field that the address is of this team or lives elsewhere", async () => {
    invite.mockResolvedValue({ ok: false, code: "already_in_team", error: "Esa dirección ya es de una persona de este equipo." });
    render(panel(open));
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Correo del propietario"), "ya@acme.test");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText("Esa dirección ya es de una persona de este equipo.")).toBeTruthy();
    expect(screen.getByLabelText("Correo del propietario").getAttribute("aria-invalid")).toBe("true");
  });

  it("with an active owner there is no form and no switched-off button: just nothing", () => {
    const { container } = render(
      panel({ ...open, has_active_owner: true, can_invite: false, can_resend: false }),
    );
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("with the console off there is no form: it says to switch it on, with the link", () => {
    render(panel({ ...open, can_invite: false, can_resend: false, block: "console_off" }));
    expect(screen.queryByLabelText("Correo del propietario")).toBeNull();
    expect(screen.queryByRole("button", { name: "Invitar" })).toBeNull();
    expect(document.body.textContent).toMatch(/consola .* apagada/);
    expect(screen.getByRole("link", { name: "Módulos" }).getAttribute("href")).toBe("/partners/p1/modules");
  });

  it("suspended: it cannot be invited, and it says it is suspended", () => {
    render(panel({ ...open, can_invite: false, can_resend: false, block: "suspended" }));
    expect(screen.queryByLabelText("Correo del propietario")).toBeNull();
    expect(document.body.textContent).toMatch(/suspendido/);
  });

  it("an expired invitation is said with its date, and its address goes first in the form", () => {
    render(
      panel({
        ...open,
        expired_email: "vieja@acme.test",
        expired_at: "2026-11-01T10:00:00Z",
        suggested_email: "vieja@acme.test",
      }),
    );
    const notice = screen.getByRole("alert");
    expect(notice.textContent).toMatch("vieja@acme.test");
    expect(notice.textContent).toMatch("1 de noviembre de 2026");
    expect((screen.getByLabelText("Correo del propietario") as HTMLInputElement).value).toBe("vieja@acme.test");
  });

  it("an expired invitation is said even if nothing can be done yet", () => {
    render(
      panel({
        ...open,
        can_invite: false,
        can_resend: false,
        block: "console_off",
        expired_email: "vieja@acme.test",
        expired_at: "2026-11-01T10:00:00Z",
      }),
    );
    expect(document.body.textContent).toMatch("vieja@acme.test");
    expect(document.body.textContent).toMatch("1 de noviembre de 2026");
  });

  // ── R2.6, R2.7: el estado de la invitación ───────────────────────────────

  it("a sent invitation says so and when, and explains what sent means in one line", () => {
    render(panel(live, [row]));
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("duena@acme.test")).toBeTruthy();
    expect(within(item).getByText("Enviada hace 2 h")).toBeTruthy();
    expect(item.textContent).toMatch("24 de noviembre de 2026");
    expect(document.body.textContent).toMatch(/el proveedor de correo la aceptó/);
    expect(document.body.textContent).not.toMatch(/entregad|recibid/i);
  });

  it("without a date it says the send is not on record, never that it was sent", () => {
    render(panel(live, [{ ...row, sentAgo: null }]));
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("No consta el envío")).toBeTruthy();
    expect(item.textContent).not.toMatch(/Enviada/);
    expect(within(item).getByRole("button", { name: /Reenviar/ })).toBeTruthy();
  });

  // ── R4: reenviar ─────────────────────────────────────────────────────────

  it("resending shows the result and says the previous link no longer works", async () => {
    resend.mockResolvedValue({ ok: true, data: result });
    render(panel(live, [row]));
    await userEvent.setup().click(screen.getByRole("button", { name: /Reenviar/ }));
    await vi.waitFor(() => expect(resend).toHaveBeenCalledWith("p1", "i1"));
    expect(await screen.findByText("https://console.test/invite/tok-nuevo")).toBeTruthy();
    expect(document.body.textContent).toMatch(/enlace anterior ya no sirve/);
  });

  it("blocks both actions while a request lasts", async () => {
    let answer: (v: unknown) => void = () => {};
    resend.mockReturnValue(new Promise((r) => (answer = r)));
    render(panel(live, [row]));
    await userEvent.setup().click(screen.getByRole("button", { name: /Reenviar/ }));
    const busy = await screen.findByRole("button", { name: /Reenviando/ });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Revocar/ }) as HTMLButtonElement).disabled).toBe(true);
    answer({ ok: true, data: result });
    await screen.findByText("https://console.test/invite/tok-nuevo");
  });

  it("if the person just accepted it says so, and no dead link stays on screen", async () => {
    resend.mockResolvedValue({ ok: false, code: "invitation_accepted", error: "Esa persona ya aceptó la invitación: ya está dentro." });
    render(panel(live, [row]));
    await userEvent.setup().click(screen.getByRole("button", { name: /Reenviar/ }));
    expect(await screen.findByText(/ya aceptó/)).toBeTruthy();
    expect(screen.queryByText(/console.test\/invite/)).toBeNull();
  });

  it.each([
    [{ ...live, can_resend: false, block: "console_off" as const }, /consola .* apagada/],
    [{ ...live, can_resend: false, block: "suspended" as const }, /suspendido/],
    [{ ...live, can_resend: false, has_active_owner: true }, /propietario activo/],
  ])("no resend when it is not possible, revoke stays, and it says why (%#)", (owner, reason) => {
    render(panel(owner, [row]));
    expect(screen.queryByRole("button", { name: /Reenviar/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Revocar/ })).toBeTruthy();
    expect(document.body.textContent).toMatch(reason);
  });

  it.each([
    [{ ...live, can_resend: false, block: "console_off" as const }],
    [{ ...live, can_resend: false, block: "suspended" as const }],
  ])("warns that whoever accepts will find no access (%#)", (owner) => {
    render(panel(owner, [row]));
    expect(document.body.textContent).toMatch(/quien acepte .* no tiene acceso/i);
  });

  // ── el enlace solo existe en esta vista ───────────────────────────────

  it("while a link is on screen nothing can take it away, not even refreshing the page", async () => {
    resend.mockResolvedValue({ ok: true, data: { ...result, email_sent: false, last_sent_at: null } });
    render(panel(live, [row]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Reenviar/ }));
    expect(await screen.findByText("https://console.test/invite/tok-nuevo")).toBeTruthy();

    // Refrescar puede fallar justo ahora y desmontar la pestaña, con el único
    // enlace dentro. Se refresca cuando el operador sale.
    expect(refresh).not.toHaveBeenCalled();
    // Y no hay otra fila a la que darle: una negativa se llevaría el enlace.
    expect(screen.queryByRole("button", { name: "Reenviar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Revocar" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Entendido" }));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("https://console.test/invite/tok-nuevo")).toBeNull();
    expect(screen.getByRole("button", { name: "Reenviar" })).toBeTruthy();
    // El botón pulsado ya no está: el foco no se queda en el vacío.
    expect(document.activeElement).not.toBe(document.body);
  });

  it("what happened to a dead invitation stays said after refreshing", async () => {
    resend.mockResolvedValue({ ok: false, code: "invitation_accepted", error: "Esa persona ya aceptó la invitación: ya está dentro." });
    render(panel(live, [row]));
    await userEvent.setup().click(screen.getByRole("button", { name: /Reenviar/ }));
    expect(await screen.findByText(/ya aceptó/)).toBeTruthy();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  // ── R5: revocar ──────────────────────────────────────────────────────────

  it("asks before revoking, naming the address and the link, and then does it", async () => {
    revoke.mockResolvedValue({ ok: true, data: { id: "i1", email: "duena@acme.test", status: "revoked", changed: true } });
    render(panel(live, [row]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Revocar/ }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toMatch("duena@acme.test");
    expect(dialog.textContent).toMatch(/enlace/);
    expect(dialog.textContent).toMatch(/no se le avisa/i);
    expect(revoke).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Revocar invitación" }));
    await vi.waitFor(() => expect(revoke).toHaveBeenCalledWith("p1", "i1"));
    expect(await screen.findByText(/ese enlace ya no sirve/)).toBeTruthy();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("a revoke that changed nothing does not claim the partner's link died", async () => {
    revoke.mockResolvedValue({ ok: true, data: { id: "i1", email: "duena@acme.test", status: "revoked", changed: false } });
    render(panel(live, [row]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Revocar/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Revocar invitación" }));
    expect(await screen.findByText(/ya no estaba viva/)).toBeTruthy();
    expect(screen.queryByText(/ese enlace ya no sirve/)).toBeNull();
  });

  it("if the person already accepted it says they are inside and revokes nothing", async () => {
    revoke.mockResolvedValue({ ok: false, code: "invitation_accepted", error: "Esa persona ya aceptó la invitación: ya está dentro." });
    render(panel(live, [row]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Revocar/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Revocar invitación" }));
    expect(await screen.findByText(/ya está dentro/)).toBeTruthy();
  });

  it("the long address does not get hard-coded widths: it can break", () => {
    const long = `${"muy-larga-direccion-de-correo-".repeat(4)}@un-dominio-bastante-largo.test`;
    render(panel(live, [{ ...row, email: long }]));
    expect(screen.getByText(long).className).toMatch(/wrap-anywhere|break-all/);
  });
});
