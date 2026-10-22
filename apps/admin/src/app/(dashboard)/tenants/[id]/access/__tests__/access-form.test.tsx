import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClientAccessOut, ClientReservasOut } from "@/lib/backend";

const h = vi.hoisted(() => ({ set: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock("../actions", () => ({
  setAccessAction: (...args: unknown[]) => h.set(...args),
  inviteAction: vi.fn(),
  resendAction: vi.fn(),
  revokeAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: h.error } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const { AccessForm } = await import("../access-form");
const { MembersList } = await import("../members-list");
const { kindPreview } = await import("../messages");

function access(o: Partial<ClientAccessOut> = {}): ClientAccessOut {
  return {
    eligible: true,
    ineligible_reason: null,
    partner: { id: "p1", name: "Amacrux" },
    whatsapp_connected: false,
    enabled: false,
    modules: [],
    members: [],
    reservas: null,
    ...o,
  };
}

function reservas(o: Partial<ClientReservasOut> = {}): ClientReservasOut {
  return { mode: "capacity", capacity_kind: "restaurant", live_future: 0, agents_pending_promotion: [], ...o };
}

const saveButton = () => screen.getByRole("button", { name: "Guardar acceso" });

beforeEach(() => {
  h.set.mockReset();
  h.success.mockReset();
  h.error.mockReset();
});

/** Spec 030 (R1.1, R1.3, R1.9): the operator's access tab. */
describe("AccessForm", () => {
  it("does not let the inbox be chosen without a connected WhatsApp, and says why", () => {
    render(<AccessForm tenantId="t1" access={access()} />);
    const inbox = screen.getByRole("checkbox", { name: /Bandeja de entrada/ });
    // base-ui pinta la casilla como un `span role="checkbox"`: el estado va en atributos.
    expect(inbox.getAttribute("aria-disabled") === "true" || inbox.hasAttribute("data-disabled")).toBe(true);
    expect(screen.getByText(/necesita un WhatsApp conectado/)).toBeTruthy();
  });

  it("cannot save access switched on without modules", async () => {
    render(<AccessForm tenantId="t1" access={access()} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Consola lite encendida/ }));
    const save = saveButton();
    expect(save).toHaveProperty("disabled", true);
    expect(screen.getByText(/Elige al menos un módulo/)).toBeTruthy();
    await userEvent.click(screen.getByRole("checkbox", { name: /^Panel/ }));
    expect(save).toHaveProperty("disabled", false);
  });

  it("sends only what changed, modules in sidebar order", async () => {
    h.set.mockResolvedValue({ ok: true, data: access({ enabled: true, modules: ["panel", "usage"] }) });
    render(<AccessForm tenantId="t1" access={access({ whatsapp_connected: true })} />);
    const save = saveButton();
    expect(save).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("checkbox", { name: /Consola lite encendida/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^Consumo/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^Panel/ }));
    await userEvent.click(save);
    expect(h.set).toHaveBeenCalledWith("t1", { enabled: true, modules: ["panel", "usage"] });
  });

  it("replaces the form with the reason when the client is not eligible", () => {
    render(<AccessForm tenantId="t1" access={access({ eligible: false, ineligible_reason: "no_partner", partner: null })} />);
    expect(screen.getByText(/no está en ningún partner/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Guardar acceso" })).toBeNull();
  });
});

/** Spec 043 (R1.2, R1.4, R1.5, R9.1): Reservas, its mode and its kind. */
describe("AccessForm — Reservas", () => {
  it("lists Reservas between the inbox and Consumo, without asking for a mode while it is off", () => {
    render(<AccessForm tenantId="t1" access={access()} />);
    const inbox = screen.getByRole("checkbox", { name: /^Bandeja de entrada/ });
    const reservasBox = screen.getByRole("checkbox", { name: /^Reservas/ });
    const usage = screen.getByRole("checkbox", { name: /^Consumo/ });
    expect(inbox.compareDocumentPosition(reservasBox) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(reservasBox.compareDocumentPosition(usage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Cómo reserva el negocio" })).toBeNull();
  });

  it("asks for the mode once Reservas is checked and cannot save until it is chosen", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(<AccessForm tenantId="t1" access={access({ enabled: true, modules: ["panel"] })} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /^Reservas/ }));
    const group = screen.getByRole("group", { name: "Cómo reserva el negocio" });
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect(saveButton()).toHaveProperty("disabled", true);
    const hint = screen.getByText("Elige cómo reserva el negocio.");
    expect(group.getAttribute("aria-describedby")).toContain(hint.id);
    // Servicios has no kind.
    expect(screen.queryByRole("combobox", { name: "Tipo de negocio" })).toBeNull();
    await userEvent.click(within(group).getByRole("radio", { name: /^Servicios — citas con una persona del equipo/ }));
    expect(screen.queryByText("Elige cómo reserva el negocio.")).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Tipo de negocio" })).toBeNull();
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenCalledWith("t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "services" },
    });
  });

  it("with Aforo asks for the business kind and shows its starting values", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(<AccessForm tenantId="t1" access={access({ enabled: true, modules: ["panel"] })} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /^Reservas/ }));
    await userEvent.click(screen.getByRole("radio", { name: /^Aforo — personas por hora, sin mesas/ }));
    const kind = screen.getByRole("combobox", { name: "Tipo de negocio" });
    expect(saveButton()).toHaveProperty("disabled", true);
    const hint = screen.getByText("Elige el tipo de negocio.");
    expect(kind.getAttribute("aria-describedby")).toContain(hint.id);
    expect(kind.getAttribute("aria-invalid")).toBe("true");

    await userEvent.selectOptions(kind, "restaurant");
    const preview = screen.getByText(/Aforo 64 · mesa 1 h 30 · hasta 10 por reserva · 6 guardadas/);
    expect(kind.getAttribute("aria-describedby")).toContain(preview.id);
    await userEvent.selectOptions(kind, "bar");
    expect(screen.getByText(/Aforo 80 · mesa 2 h · hasta 12 por reserva · 16 guardadas/)).toBeTruthy();
    expect(saveButton()).toHaveProperty("disabled", false);
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenCalledWith("t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "capacity", capacity_kind: "bar" },
    });
  });

  it("offers the six business kinds with their names", async () => {
    render(<AccessForm tenantId="t1" access={access({ enabled: true, modules: ["panel"] })} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /^Reservas/ }));
    await userEvent.click(screen.getByRole("radio", { name: /^Aforo/ }));
    const kind = screen.getByRole("combobox", { name: "Tipo de negocio" });
    const names = within(kind)
      .getAllByRole("option")
      .filter((o) => (o as HTMLOptionElement).value !== "")
      .map((o) => o.textContent);
    expect(names).toEqual([
      "Restaurante",
      "Bar y terraza",
      "Clases y gimnasio",
      "Tours y experiencias",
      "Salas y eventos",
      "Spa y circuitos",
    ]);
  });

  it("preselects the stored mode and kind, and does not resend them when another module changes", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(
      <AccessForm
        tenantId="t1"
        access={access({ enabled: true, whatsapp_connected: true, modules: ["panel", "reservas"], reservas: reservas() })}
      />,
    );
    expect(screen.getByRole("radio", { name: /^Aforo/ })).toHaveProperty("checked", true);
    expect(screen.getByRole("combobox", { name: "Tipo de negocio" })).toHaveProperty("value", "restaurant");
    expect(saveButton()).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("checkbox", { name: /^Consumo/ }));
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenCalledWith("t1", { enabled: true, modules: ["panel", "reservas", "usage"] });
  });

  it("sends the stored mode again when Reservas is switched back on", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(
      <AccessForm
        tenantId="t1"
        access={access({ enabled: true, modules: ["panel"], reservas: reservas({ mode: "services", capacity_kind: null }) })}
      />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: /^Reservas/ }));
    expect(screen.getByRole("radio", { name: /^Servicios/ })).toHaveProperty("checked", true);
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenCalledWith("t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "services" },
    });
  });

  it("switching Reservas off sends no Reservas settings", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(
      <AccessForm tenantId="t1" access={access({ enabled: true, modules: ["panel", "reservas"], reservas: reservas() })} />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: /^Reservas/ }));
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenCalledWith("t1", { enabled: true, modules: ["panel"] });
  });

  it("changing only the kind never asks about live reservations", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(
      <AccessForm
        tenantId="t1"
        access={access({ enabled: true, modules: ["panel", "reservas"], reservas: reservas({ live_future: 3 }) })}
      />,
    );
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Tipo de negocio" }), "bar");
    // The numbers are the business's: a new kind only renames them.
    expect(screen.queryByText(/Aforo 80/)).toBeNull();
    expect(screen.getByText(/solo cambia las palabras/)).toBeTruthy();
    await userEvent.click(saveButton());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(h.set).toHaveBeenCalledWith("t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "capacity", capacity_kind: "bar" },
    });
  });

  it("changing the mode with live reservations asks first, then cancels and notifies", async () => {
    h.set.mockResolvedValue({ ok: true, data: access() });
    render(
      <AccessForm
        tenantId="t1"
        access={access({ enabled: true, modules: ["panel", "reservas"], reservas: reservas({ live_future: 3 }) })}
      />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /^Servicios/ }));
    await userEvent.click(saveButton());
    expect(h.set).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Hay 3 reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp."),
    ).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelarlas y cambiar" }));
    expect(h.set).toHaveBeenCalledWith("t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "services", on_live: "cancel_and_notify" },
    });
    expect(h.success).toHaveBeenCalled();
  });

  it("«No cambiar» sends nothing and puts the stored mode back", async () => {
    render(
      <AccessForm
        tenantId="t1"
        access={access({ enabled: true, modules: ["panel", "reservas"], reservas: reservas({ live_future: 1 }) })}
      />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /^Servicios/ }));
    await userEvent.click(saveButton());
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/^Hay 1 reserva futura\./)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "No cambiar" }));
    expect(h.set).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: /^Aforo/ })).toHaveProperty("checked", true);
    expect(screen.getByRole("combobox", { name: "Tipo de negocio" })).toHaveProperty("value", "restaurant");
  });

  it("a 409 for live reservations (a race) offers the same choice with the server's count", async () => {
    h.set
      .mockResolvedValueOnce({ ok: false, error: "Hay reservas futuras.", code: "live_reservations", count: 2 })
      .mockResolvedValueOnce({ ok: true, data: access() });
    render(
      <AccessForm
        tenantId="t1"
        access={access({
          enabled: true,
          modules: ["panel", "reservas"],
          reservas: reservas({ mode: "services", capacity_kind: null, live_future: 0 }),
        })}
      />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /^Aforo/ }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Tipo de negocio" }), "rooms");
    await userEvent.click(saveButton());
    expect(h.set).toHaveBeenNthCalledWith(1, "t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "capacity", capacity_kind: "rooms" },
    });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/^Hay 2 reservas futuras\./)).toBeTruthy();
    expect(h.error).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelarlas y cambiar" }));
    expect(h.set).toHaveBeenNthCalledWith(2, "t1", {
      enabled: true,
      modules: ["panel", "reservas"],
      reservas: { mode: "capacity", capacity_kind: "rooms", on_live: "cancel_and_notify" },
    });
  });

  it("links each agent with a version waiting to be promoted to its Agent tab", () => {
    render(
      <AccessForm
        tenantId="t1"
        access={access({
          enabled: true,
          modules: ["panel", "reservas"],
          reservas: reservas({
            agents_pending_promotion: [
              { agent_id: "a1", name: "Agente de reservas", version: 7 },
              { agent_id: "a2", name: "Recepción", version: 3 },
            ],
          }),
        })}
      />,
    );
    expect(
      screen.getByText(
        "Hay una versión del agente preparada con las herramientas de Reservas. Revísala y promuévela en la pestaña Agente.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: /Agente de reservas.*versión 7/ }).getAttribute("href")).toBe(
      "/tenants/t1/agent?agent=a1",
    );
    expect(screen.getByRole("link", { name: /Recepción.*versión 3/ }).getAttribute("href")).toBe(
      "/tenants/t1/agent?agent=a2",
    );
  });

  it("says nothing about the agent when no version is waiting", () => {
    render(<AccessForm tenantId="t1" access={access({ modules: ["reservas"], reservas: reservas() })} />);
    expect(screen.queryByText(/versión del agente preparada/)).toBeNull();
  });
});

/** data-model.md, «Valores de partida por tipo». */
describe("kindPreview", () => {
  it.each([
    ["restaurant", "Aforo 64 · mesa 1 h 30 · hasta 10 por reserva · 6 guardadas"],
    ["bar", "Aforo 80 · mesa 2 h · hasta 12 por reserva · 16 guardadas"],
    ["classes", "Aforo 20 · sesión 1 h · hasta 2 por reserva · 2 guardadas"],
    ["tours", "Aforo 16 · tour 2 h · hasta 8 por reserva · sin guardadas"],
    ["rooms", "Aforo 120 · sala 2 h · hasta 40 por reserva · sin guardadas"],
    ["spa", "Aforo 14 · circuito 1 h 30 · hasta 4 por reserva · 2 guardadas"],
  ] as const)("%s", (kind, expected) => {
    expect(kindPreview(kind)).toBe(expected);
  });
});

describe("MembersList", () => {
  it("shows each state and an empty state", () => {
    const { rerender } = render(<MembersList tenantId="t1" members={[]} />);
    expect(screen.getByText("Nadie tiene acceso todavía.")).toBeTruthy();
    rerender(
      <MembersList
        tenantId="t1"
        members={[
          { id: "1", kind: "member", email: "a@x.test", name: "Ana", status: "active", since: "2026-10-01T00:00:00Z", expires_at: null },
          { id: "2", kind: "invitation", email: "b@x.test", name: null, status: "pending", since: null, expires_at: "2026-10-29T00:00:00Z" },
          { id: "3", kind: "invitation", email: "c@x.test", name: null, status: "expired", since: null, expires_at: "2026-09-01T00:00:00Z" },
          { id: "4", kind: "member", email: "d@x.test", name: null, status: "revoked", since: null, expires_at: null },
        ]}
      />,
    );
    expect(screen.getByText("Activa")).toBeTruthy();
    expect(screen.getByText("Invitación pendiente")).toBeTruthy();
    expect(screen.getByText("Invitación caducada")).toBeTruthy();
    expect(screen.getByText("Revocada")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Reenviar/ })).toHaveLength(2);
  });
});
