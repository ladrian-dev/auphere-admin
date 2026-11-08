import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAccess, ClientAccessMember, ClientInvitation } from "@/lib/backend/client-access";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const actions = vi.hoisted(() => ({
  inviteClientMemberAction: vi.fn(),
  resendClientMemberAction: vi.fn(),
  revokeClientMemberAction: vi.fn(),
  reloadClientAccessAction: vi.fn(),
  setClientAccessAction: vi.fn(),
}));
vi.mock("@/app/(console)/clients/[ref]/access/actions", () => actions);

const { ClientPeopleCard } = await import("../client-people-card");

/**
 * Spec 056 (requisitos 3.4 a 3.7; guías de Apple) — «Personas». Cada fila tiene
 * una sola acción a la vista, la principal para su estado (Reenviar a una
 * invitada o caducada); el resto va en «⋯», con «Revocar» al final, en rojo y
 * con confirmación. El enlace de una invitación se enseña una vez. Y los cinco
 * estados: cargando (la ruta), vacío, error, parcial e ideal.
 */

const ANA: ClientAccessMember = { id: "m-ana", kind: "member", email: "ana@negocio.test", name: "Ana", status: "active", since: "2026-11-01T10:00:00Z" };
const LUIS: ClientAccessMember = { id: "i-luis", kind: "invitation", email: "luis@negocio.test", name: null, status: "pending", expires_at: "2026-11-29T10:00:00Z" };
const EVA: ClientAccessMember = { id: "i-eva", kind: "invitation", email: "eva@negocio.test", name: "Eva", status: "expired", expires_at: "2026-10-01T10:00:00Z" };
const OLD: ClientAccessMember = { id: "m-old", kind: "member", email: "old@negocio.test", name: null, status: "revoked" };

function access(over: Partial<ClientAccess> = {}): ClientAccess {
  return { eligible: true, ineligible_reason: null, whatsapp_connected: true, enabled: true, modules: ["panel"], members: [ANA, LUIS, EVA, OLD], ...over };
}

const invitation = (over: Partial<ClientInvitation> = {}): ClientInvitation => ({
  id: "i-new",
  email: "marta@negocio.test",
  status: "pending",
  expires_at: "2026-11-29T10:00:00Z",
  accept_path: "/invite/tok",
  accept_url: "https://console.test/invite/tok",
  email_sent: true,
  ...over,
});

/** Lo que el padre hace con `onMembers`: guardar la lista y volver a pintar. */
function Harness({ initial, onRetry = () => {} }: { initial: ClientAccess | null; onRetry?: () => void }) {
  const [a, setA] = React.useState(initial);
  return <ClientPeopleCard refId="flor" access={a} onMembers={(members) => setA((p) => (p ? { ...p, members } : p))} onRetry={onRetry} />;
}

function paint(initial: ClientAccess | null = access(), onRetry?: () => void) {
  return render(
    <LocaleProvider locale="es">
      <Harness initial={initial} onRetry={onRetry} />
    </LocaleProvider>,
  );
}

const row = (email: string) => screen.getAllByRole("listitem").find((li) => within(li).queryByText(new RegExp(email.replace(".", "\\.")))) as HTMLElement;
const visibleButtons = (li: HTMLElement) => within(li).queryAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);

beforeEach(() => {
  for (const fn of Object.values(actions)) fn.mockReset();
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("Personas · una acción a la vista por fila (3.5)", () => {
  it("una invitada: Reenviar a la vista y Revocar en «⋯»; una caducada: solo Reenviar; una activa: solo «⋯»; lo revocado, nada", () => {
    paint();
    expect(visibleButtons(row("luis@negocio.test"))).toEqual(["Reenviar la invitación a luis@negocio.test", "Más acciones de luis@negocio.test"]);
    expect(visibleButtons(row("eva@negocio.test"))).toEqual(["Reenviar la invitación a eva@negocio.test"]);
    expect(visibleButtons(row("ana@negocio.test"))).toEqual(["Más acciones de Ana"]);
    expect(visibleButtons(row("old@negocio.test"))).toEqual([]);
  });

  it("cada fila dice su estado en palabras (3.4)", () => {
    paint();
    expect(within(row("ana@negocio.test")).getByText("Activa")).toBeVisible();
    expect(within(row("luis@negocio.test")).getByText("Invitada")).toBeVisible();
    expect(within(row("eva@negocio.test")).getByText("Caducada")).toBeVisible();
    expect(within(row("old@negocio.test")).getByText("Revocada")).toBeVisible();
  });

  it("«Revocar» va el último del menú, en rojo", async () => {
    const user = userEvent.setup();
    paint();
    await user.click(screen.getByRole("button", { name: "Más acciones de Ana" }));
    const items = await screen.findAllByRole("menuitem");
    expect(items.at(-1)).toHaveTextContent("Revocar el acceso");
    expect(items.at(-1)).toHaveAttribute("data-variant", "destructive");
  });

  it("pasa axe", async () => {
    const { container } = paint();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Personas · revocar pide confirmación (3.5, 3.7)", () => {
  it("revocar a una persona pregunta, dice que se cierran sus sesiones y, al confirmar, la fila queda revocada", async () => {
    const user = userEvent.setup();
    actions.revokeClientMemberAction.mockResolvedValue({ ok: true, data: { member: { ...ANA, status: "revoked" } } });
    paint();
    await user.click(screen.getByRole("button", { name: "Más acciones de Ana" }));
    await user.click(await screen.findByRole("menuitem", { name: "Revocar el acceso" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Revocar el acceso?" });
    expect(dialog).toHaveTextContent("ana@negocio.test dejará de entrar en la consola y en la app");
    expect(actions.revokeClientMemberAction).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Revocar" }));
    await waitFor(() => expect(actions.revokeClientMemberAction).toHaveBeenCalledWith({ ref: "flor", member: "m-ana" }));
    await waitFor(() => expect(within(row("ana@negocio.test")).getByText("Revocada")).toBeVisible());
    expect(toast.success).toHaveBeenCalledWith("ana@negocio.test ya no tiene acceso");
  });

  it("cancelar no revoca nada", async () => {
    const user = userEvent.setup();
    paint();
    await user.click(screen.getByRole("button", { name: "Más acciones de luis@negocio.test" }));
    await user.click(await screen.findByRole("menuitem", { name: "Revocar la invitación" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Revocar la invitación?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(actions.revokeClientMemberAction).not.toHaveBeenCalled();
    expect(within(row("luis@negocio.test")).getByText("Invitada")).toBeVisible();
  });

  it("si la API dice que no, el diálogo se queda abierto con la frase, nunca el texto técnico", async () => {
    const user = userEvent.setup();
    actions.revokeClientMemberAction.mockResolvedValue({ ok: false, status: 404, message: "unknown member", code: "unknown_member" });
    paint();
    await user.click(screen.getByRole("button", { name: "Más acciones de Ana" }));
    await user.click(await screen.findByRole("menuitem", { name: "Revocar el acceso" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Revocar el acceso?" });
    await user.click(within(dialog).getByRole("button", { name: "Revocar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Esa persona ya no está en la lista. Recarga la página.");
    expect(dialog).not.toHaveTextContent("unknown member");
  });
});

describe("Personas · invitar y el enlace una sola vez (3.6)", () => {
  it("invita, enseña el enlace con su resultado y la invitación entra en la lista", async () => {
    const user = userEvent.setup();
    actions.inviteClientMemberAction.mockResolvedValue({ ok: true, data: invitation() });
    paint();
    await user.type(screen.getByRole("textbox", { name: /Correo/ }), "marta@negocio.test");
    await user.type(screen.getByRole("textbox", { name: /Nombre/ }), "Marta");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    await waitFor(() => expect(actions.inviteClientMemberAction).toHaveBeenCalledWith({ ref: "flor", email: "marta@negocio.test", name: "Marta" }));
    expect(await screen.findByText("Invitación enviada a marta@negocio.test")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Enlace de la invitación de marta@negocio.test" })).toHaveValue("https://console.test/invite/tok");
    expect(within(row("marta@negocio.test")).getByText("Invitada")).toBeVisible();
    // El formulario queda limpio para la siguiente.
    expect(screen.getByRole("textbox", { name: /Correo/ })).toHaveValue("");
  });

  it("si el correo no salió, lo dice como alerta y el enlace sigue a mano", async () => {
    const user = userEvent.setup();
    actions.inviteClientMemberAction.mockResolvedValue({ ok: true, data: invitation({ email_sent: false }) });
    paint();
    await user.type(screen.getByRole("textbox", { name: /Correo/ }), "marta@negocio.test");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("El correo a marta@negocio.test no salió");
    expect(screen.getByRole("textbox", { name: "Enlace de la invitación de marta@negocio.test" })).toHaveValue("https://console.test/invite/tok");
  });

  it("cerrar el aviso se lleva el enlace: no vuelve", async () => {
    const user = userEvent.setup();
    actions.inviteClientMemberAction.mockResolvedValue({ ok: true, data: invitation() });
    paint();
    await user.type(screen.getByRole("textbox", { name: /Correo/ }), "marta@negocio.test");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    await user.click(await screen.findByRole("button", { name: "Cerrar el aviso de marta@negocio.test" }));
    expect(screen.queryByRole("textbox", { name: "Enlace de la invitación de marta@negocio.test" })).toBeNull();
  });

  it("un correo mal escrito no viaja", async () => {
    const user = userEvent.setup();
    paint();
    await user.type(screen.getByRole("textbox", { name: /Correo/ }), "marta");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText("Escribe un correo válido, como nombre@negocio.com")).toBeVisible();
    expect(actions.inviteClientMemberAction).not.toHaveBeenCalled();
  });

  it("los no de la API se dicen en palabras (la cuenta de un partner, el límite)", async () => {
    const user = userEvent.setup();
    actions.inviteClientMemberAction.mockResolvedValueOnce({ ok: false, status: 409, message: "x", code: "account_is_partner_member" });
    actions.inviteClientMemberAction.mockResolvedValueOnce({ ok: false, status: 429, message: "x", code: "rate_limited" });
    paint();
    const email = screen.getByRole("textbox", { name: /Correo/ });
    await user.type(email, "socio@agencia.test");
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText(/Ese correo es de un equipo de partner/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText(/Demasiadas invitaciones seguidas/)).toBeVisible();
  });

  it("reenviar da otro enlace y la invitación de antes queda revocada", async () => {
    const user = userEvent.setup();
    actions.resendClientMemberAction.mockResolvedValue({ ok: true, data: invitation({ id: "i-luis-2", email: "luis@negocio.test" }) });
    paint();
    await user.click(screen.getByRole("button", { name: "Reenviar la invitación a luis@negocio.test" }));
    await waitFor(() => expect(actions.resendClientMemberAction).toHaveBeenCalledWith({ ref: "flor", member: "i-luis" }));
    expect(await screen.findByRole("textbox", { name: "Enlace de la invitación de luis@negocio.test" })).toBeVisible();
    const rows = screen.getAllByRole("listitem").filter((li) => within(li).queryByText(/luis@negocio\.test/));
    expect(rows.map((li) => li.getAttribute("data-status"))).toEqual(["pending", "revoked"]);
  });
});

describe("Personas · los cinco estados", () => {
  it("vacío: nadie todavía, con el formulario para invitar", () => {
    paint(access({ members: [] }));
    expect(screen.getByText("Aún no hay nadie")).toBeVisible();
    expect(screen.getByRole("button", { name: "Invitar" })).toBeVisible();
  });

  it("parcial: con la consola apagada se ve la lista pero no se invita", () => {
    paint(access({ enabled: false }));
    expect(screen.getByText(/La consola está apagada/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Invitar" })).toBeNull();
    expect(row("ana@negocio.test")).toBeTruthy();
  });

  it("error: lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    paint(null, retry);
    expect(screen.getByText("No pudimos leer el acceso de este cliente")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("textos largos no rompen la fila (alemán, +30 %)", () => {
    const long = "Bartholomäus-Friedrichsen-Schwarzenegger@sehr-langer-unternehmensname.example";
    paint(access({ members: [{ ...ANA, name: "Bartholomäus Friedrichsen von Hohenzollern-Sigmaringen", email: long }] }));
    const li = screen.getAllByRole("listitem")[0]!;
    expect(li.className).toMatch(/min-w-0/);
    expect(within(li).getByText(/Bartholomäus Friedrichsen/).className).toMatch(/break-words/);
  });
});
