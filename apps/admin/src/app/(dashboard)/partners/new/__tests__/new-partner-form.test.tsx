import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const createPartner = vi.fn();
const resend = vi.fn();
const push = vi.fn();
const toastSuccess = vi.fn();

vi.mock("../../actions", () => ({ createPartnerAction: (...a: unknown[]) => createPartner(...a) }));
vi.mock("../../_invitation/actions", () => ({
  resendOwnerInvitationAction: (...a: unknown[]) => resend(...a),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }));

import { NewPartnerForm } from "../new-partner-form";

const created = {
  id: "p1",
  name: "Acme",
  slug: "acme",
  console_enabled: true,
  invitation: {
    id: "i1",
    email: "duena@acme.test",
    role: "owner",
    status: "pending",
    expires_at: "2026-11-24T19:00:00Z",
    created_at: "2026-11-03T19:00:00Z",
    last_sent_at: "2026-11-03T19:00:01Z",
    email_sent: true,
    accept_url: "https://console.test/invite/tok-en",
  },
};

async function fill(values: { name?: string; slug?: string; email?: string }) {
  const user = userEvent.setup();
  if (values.name) await user.type(screen.getByLabelText("Nombre"), values.name);
  if (values.slug) await user.type(screen.getByLabelText(/Identificador/), values.slug);
  if (values.email) await user.type(screen.getByLabelText("Correo del propietario"), values.email);
  return user;
}

describe("NewPartnerForm (spec 052)", () => {
  beforeEach(() => {
    createPartner.mockReset();
    resend.mockReset();
    push.mockReset();
    toastSuccess.mockReset();
    createPartner.mockResolvedValue({ ok: true, data: created });
  });

  it("asks for the owner's address and says what creating will do, before it is sent", () => {
    render(<NewPartnerForm />);
    expect(screen.getByLabelText("Correo del propietario")).toBeTruthy();
    const page = document.body.textContent ?? "";
    expect(page).toMatch(/se enciende su consola/);
    expect(page).toMatch(/propietari/);
    // R1.11: no se pide un contacto aparte.
    expect(screen.queryByLabelText(/contacto/i)).toBeNull();
  });

  it("refuses an empty address and says so in the field", async () => {
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    expect(await screen.findByText("Escribe el correo de quien va a ser su propietario.")).toBeTruthy();
    expect(screen.getByLabelText("Correo del propietario").getAttribute("aria-invalid")).toBe("true");
    expect(createPartner).not.toHaveBeenCalled();
  });

  it("refuses something that is not an address", async () => {
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "no-es-un-correo" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    expect(await screen.findByText("Eso no tiene forma de correo.")).toBeTruthy();
    expect(createPartner).not.toHaveBeenCalled();
  });

  it("sends the owner's address, trimmed, and never a contact", async () => {
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "  duena@acme.test " });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    await vi.waitFor(() => expect(createPartner).toHaveBeenCalled());
    expect(createPartner).toHaveBeenCalledWith({ name: "Acme", slug: "acme", owner_email: "duena@acme.test" });
  });

  it("stays on this page with the result, and does not send the operator to create a key", async () => {
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));

    expect(await screen.findByText("Invitación enviada a duena@acme.test")).toBeTruthy();
    expect(screen.getByText(/Acme ya existe/)).toBeTruthy();
    expect(screen.getByText("https://console.test/invite/tok-en")).toBeTruthy();
    // R6.6: el enlace no viaja en ninguna URL del panel, y se sale con un enlace limpio.
    expect(push).not.toHaveBeenCalled();
    const out = screen.getByRole("link", { name: "Ir a la ficha del partner" });
    expect(out.getAttribute("href")).toBe("/partners/p1");
    // R2.1, R2.10: ni un aviso que se va, ni «crea su API key».
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/API key|clave de API/i);
    expect(screen.queryByRole("button", { name: "Crear partner" })).toBeNull();
  });

  it("if a retry dies on the way, the link goes away and the way out stays", async () => {
    createPartner.mockResolvedValue({
      ok: true,
      data: { ...created, invitation: { ...created.invitation, email_sent: false, last_sent_at: null } },
    });
    resend.mockResolvedValue({ ok: false, code: "invitation_accepted", error: "Esa persona ya aceptó la invitación." });
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    await user.click(await screen.findByRole("button", { name: "Reintentar el envío" }));
    expect(await screen.findByText("Esa persona ya aceptó la invitación.")).toBeTruthy();
    expect(screen.queryByText("https://console.test/invite/tok-en")).toBeNull();
    expect(screen.getByRole("link", { name: "Ir a la ficha del partner" })).toBeTruthy();
  });

  it("says in the field that the address already has its own console", async () => {
    createPartner.mockResolvedValue({
      ok: false,
      code: "address_has_own_console",
      error: "Esa dirección ya tiene su propia consola: es de una persona de otro partner o de un cliente.",
    });
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    expect(await screen.findByText(/ya tiene su propia consola/)).toBeTruthy();
    expect(screen.getByLabelText("Correo del propietario").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("button", { name: "Crear partner" })).toBeTruthy();
  });

  it("says in the field that the identifier is taken", async () => {
    createPartner.mockResolvedValue({ ok: false, code: "slug_taken", error: "Ese identificador ya está usado." });
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    expect(await screen.findByText("Ese identificador ya está usado.")).toBeTruthy();
    expect(screen.getByLabelText(/Identificador/).getAttribute("aria-invalid")).toBe("true");
  });

  it("when the answer is lost it says the partner may exist, in a message that stays", async () => {
    createPartner.mockResolvedValue({
      ok: false,
      code: "unknown_outcome",
      error: "No pudimos confirmar si se creó. Búscalo en Partners antes de repetir.",
    });
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/Búscalo en Partners/)).toBeTruthy();
  });

  it("blocks the button while the request lasts", async () => {
    let answer: (v: unknown) => void = () => {};
    createPartner.mockReturnValue(new Promise((r) => (answer = r)));
    render(<NewPartnerForm />);
    const user = await fill({ name: "Acme", slug: "acme", email: "duena@acme.test" });
    await user.click(screen.getByRole("button", { name: "Crear partner" }));
    const busy = await screen.findByRole("button", { name: /Creando/ });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    // Hasta 25 s con el proveedor sin responder: se dice, no solo gira.
    expect(screen.getByRole("status").textContent).toMatch(/medio minuto/);
    answer({ ok: true, data: created });
    expect(await screen.findByText("Invitación enviada a duena@acme.test")).toBeTruthy();
  });
});
