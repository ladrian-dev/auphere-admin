import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ClientInvitationOut, ClientMemberOut } from "@/lib/backend";

const h = vi.hoisted(() => ({
  invite: vi.fn(),
  resend: vi.fn(),
  revoke: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  refresh: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("../actions", () => ({
  inviteAction: (...a: unknown[]) => h.invite(...a),
  resendAction: (...a: unknown[]) => h.resend(...a),
  revokeAction: (...a: unknown[]) => h.revoke(...a),
  listPhonesAction: vi.fn(),
  closePhoneAction: vi.fn(),
  setAccessAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: h.error } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: h.refresh, push: h.push, replace: h.replace }),
}));

const { PeopleSection } = await import("../people-section");

const CONSOLE = "https://console.staging.auphere.test";
const TOKEN = "tok-de-un-solo-uso-123";
const VALERIA = "valeria@flor.test";

/** What the API answers: the relative path is still in the body, and the panel must not show it. */
function invitation(o: Partial<ClientInvitationOut> & { token?: string } = {}) {
  const { token = TOKEN, ...rest } = o;
  return {
    id: `inv-${token}`,
    email: VALERIA,
    status: "pending",
    expires_at: "2026-11-24T10:00:00Z",
    accept_path: `/invite/${token}`,
    accept_url: `${CONSOLE}/invite/${token}`,
    email_sent: true,
    ...rest,
  };
}

const pendingRow = (o: Partial<ClientMemberOut> = {}): ClientMemberOut => ({
  id: "inv-1",
  kind: "invitation",
  email: VALERIA,
  name: null,
  status: "pending",
  since: null,
  expires_at: "2026-11-24T10:00:00Z",
  ...o,
});

async function invite(user: ReturnType<typeof userEvent.setup>, email = VALERIA) {
  await user.type(screen.getByLabelText("Correo"), email);
  await user.click(screen.getByRole("button", { name: "Invitar" }));
}

function people(members: ClientMemberOut[] = []) {
  return <PeopleSection tenantId="t1" disabled={false} members={members} />;
}

/** Bug enlace-de-invitacion-que-no-abre: the link the operator passes on by hand. */
describe("PeopleSection", () => {
  beforeEach(() => {
    for (const mock of Object.values(h)) mock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the absolute link, never the relative path", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation() });
    const user = userEvent.setup();
    render(people());

    await invite(user);

    const link = await screen.findByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` });
    expect(link).toHaveValue(`${CONSOLE}/invite/${TOKEN}`);
    expect(screen.queryByText(`/invite/${TOKEN}`)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(`Invitación enviada a ${VALERIA}`);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(h.success).toHaveBeenCalledWith(`Invitación enviada a ${VALERIA}`);
  });

  it("raises an alert for a failed send, with the link, and no toast", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people());

    await invite(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(`El correo a ${VALERIA} no salió`);
    expect(alert).toHaveTextContent("La invitación está creada");
    expect(screen.getByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).toHaveValue(
      `${CONSOLE}/invite/${TOKEN}`,
    );
    expect(h.success).not.toHaveBeenCalled();
    expect(h.error).not.toHaveBeenCalled();
  });

  it("does not read the token aloud: the link sits outside the live region", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people());

    await invite(user);

    expect(await screen.findByRole("alert")).not.toHaveTextContent(TOKEN);
  });

  it("keeps the failure on screen with time and across a refresh of the page", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    const { rerender } = render(people());
    await invite(user);
    await screen.findByRole("alert");
    expect(h.refresh).toHaveBeenCalled();

    vi.useFakeTimers();
    act(() => {
      vi.advanceTimersByTime(60 * 60 * 1000);
    });
    vi.useRealTimers();
    rerender(people([pendingRow({ id: "inv-tok" })]));

    expect(screen.getByRole("alert")).toHaveTextContent("no salió");
    expect(screen.getByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).toBeInTheDocument();
  });

  it("only goes away when the operator closes it", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people());
    await invite(user);
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: `Cerrar el aviso de ${VALERIA}` }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).not.toBeInTheDocument();
  });

  it("does not lose the first failure when the next person is invited", async () => {
    h.invite
      .mockResolvedValueOnce({ ok: true, data: invitation({ email_sent: false }) })
      .mockResolvedValueOnce({ ok: true, data: invitation({ token: "otro", email: "ana@flor.test" }) });
    const user = userEvent.setup();
    render(people());

    await invite(user);
    await screen.findByRole("alert");
    await invite(user, "ana@flor.test");

    await screen.findByRole("textbox", { name: "Enlace de invitación de ana@flor.test" });
    expect(screen.getByRole("alert")).toHaveTextContent(VALERIA);
    expect(screen.getByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).toHaveValue(
      `${CONSOLE}/invite/${TOKEN}`,
    );
  });

  it("replaces the notice on resend, because the previous link is dead", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    h.resend.mockResolvedValue({ ok: true, data: invitation({ token: "nuevo", email_sent: false }) });
    const user = userEvent.setup();
    render(people([pendingRow()]));
    await invite(user);
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: `Reenviar a ${VALERIA}` }));

    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).toHaveValue(
        `${CONSOLE}/invite/nuevo`,
      ),
    );
    expect(screen.getAllByRole("textbox", { name: /Enlace de invitación/ })).toHaveLength(1);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("raises the same alert when a resend does not go out", async () => {
    h.resend.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people([pendingRow()]));

    await user.click(screen.getByRole("button", { name: `Reenviar a ${VALERIA}` }));

    expect(await screen.findByRole("alert")).toHaveTextContent(`El correo a ${VALERIA} no salió`);
    expect(h.success).not.toHaveBeenCalled();
  });

  it("drops the notice when the invitation is revoked, because its link is dead", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    h.revoke.mockResolvedValue({ ok: true, data: null });
    const user = userEvent.setup();
    render(people([pendingRow()]));
    await invite(user);
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: `Revocar a ${VALERIA}` }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Revocar" }));

    await waitFor(() =>
      expect(screen.queryByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows nothing but the refusal when the invitation could not be created", async () => {
    h.invite.mockResolvedValue({ ok: false, error: "Esa persona ya tiene acceso." });
    const user = userEvent.setup();
    render(people());

    await invite(user);

    await waitFor(() =>
      expect(h.error).toHaveBeenCalledWith("No se pudo invitar", { description: "Esa persona ya tiene acceso." }),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Enlace de invitación/ })).not.toBeInTheDocument();
  });

  it("never puts the token in the address of the panel", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    h.resend.mockResolvedValue({ ok: true, data: invitation({ token: "nuevo" }) });
    const user = userEvent.setup();
    const before = window.location.href;
    render(people([pendingRow()]));

    await invite(user);
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: `Reenviar a ${VALERIA}` }));
    await screen.findByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` });

    expect(h.push).not.toHaveBeenCalled();
    expect(h.replace).not.toHaveBeenCalled();
    expect(window.location.href).toBe(before);
  });

  it("copies the absolute link, also from the keyboard", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people());
    await invite(user);
    const field = await screen.findByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` });

    field.focus();
    await user.tab();
    const copy = screen.getByRole("button", { name: `Copiar el enlace de ${VALERIA}` });
    expect(copy).toHaveFocus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(h.success).toHaveBeenCalledWith("Enlace copiado"));
    await expect(navigator.clipboard.readText()).resolves.toBe(`${CONSOLE}/invite/${TOKEN}`);
  });

  it("says so when the browser refuses to copy, and leaves the link selectable", async () => {
    h.invite.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    const user = userEvent.setup();
    render(people());
    await invite(user);
    const field = await screen.findByRole("textbox", { name: `Enlace de invitación de ${VALERIA}` });
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));

    await user.click(screen.getByRole("button", { name: `Copiar el enlace de ${VALERIA}` }));

    await waitFor(() => expect(h.error).toHaveBeenCalledWith("No se pudo copiar: selecciona el enlace a mano"));
    expect(field).toHaveAttribute("readonly");
  });
});
