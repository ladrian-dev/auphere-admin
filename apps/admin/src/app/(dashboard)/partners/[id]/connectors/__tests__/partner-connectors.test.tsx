import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "@nexus/ui/test/axe";

import type { PartnerConnector } from "@/lib/backend-connector-access";

/**
 * Spec 060, T041 y T042: la pestaña «Conectores» del partner y el diálogo que
 * comparte con la ficha del conector (requisitos 2 y 4).
 */
const h = vi.hoisted(() => ({
  setState: vi.fn(),
  setDefault: vi.fn(),
  success: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/app/(dashboard)/connectors/access-actions", () => ({
  setConnectorPartnerStateAction: (...a: unknown[]) => h.setState(...a),
  setConnectorDefaultAction: (...a: unknown[]) => h.setDefault(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { PartnerConnectorsList } = await import("../partner-connectors-list");

function item(o: Partial<PartnerConnector> = {}): PartnerConnector {
  return {
    slug: "tienda",
    display_name: "Tienda",
    category: "ecommerce",
    auth_kind: "api_key",
    default_enabled: true,
    partner_state: "default",
    effective: true,
    connected_clients: 2,
    set_by: null,
    set_at: null,
    reason: null,
    ...o,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PartnerConnectorsList", () => {
  it("says, per connector, whether its clients can use it and where that comes from", () => {
    render(
      <PartnerConnectorsList
        partnerId="p1"
        items={[
          item(),
          item({
            slug: "quedate",
            display_name: "Quédate",
            default_enabled: false,
            partner_state: "enabled",
            effective: true,
            connected_clients: 0,
            reason: "Conector propio de Amacrux",
          }),
        ]}
      />,
    );
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("Disponible")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Por defecto (habilitado)", { selector: "span" })).toBeInTheDocument();
    expect(within(rows[1]!).getByText("2 clientes")).toBeInTheDocument();
    expect(within(rows[2]!).getByText(/Decidido para este partner: Conector propio de Amacrux/)).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Ninguno")).toBeInTheDocument();
  });

  it("shows an empty state when the catalog has nothing", () => {
    render(<PartnerConnectorsList partnerId="p1" items={[]} />);
    expect(screen.getByText("No hay conectores en el catálogo")).toBeInTheDocument();
  });

  it("asks for a reason and saves the decision", async () => {
    h.setState.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item()]} />);
    await user.selectOptions(screen.getByLabelText("Decisión sobre Tienda para este partner"), "disabled");
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Guardar" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(confirm);
    expect(h.setState).toHaveBeenCalledWith("tienda", "p1", {
      state: "disabled",
      reason: "Solo para Amacrux",
      confirm: false,
    });
    expect(h.success).toHaveBeenCalledWith("Disponibilidad guardada");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("lists who loses the connector before confirming, and cancelling saves nothing", async () => {
    h.setState.mockResolvedValueOnce({
      ok: false,
      code: "confirm_required",
      impact: {
        affected: [
          {
            partner_id: "p1",
            partner_name: "Amacrux",
            clients: [{ tenant_id: "t1", name: "Quédate", connection_status: "connected", agents: 2 }],
          },
        ],
        totals: { clients: 1, agents: 2 },
      },
    });
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item()]} />);
    await user.selectOptions(screen.getByLabelText("Decisión sobre Tienda para este partner"), "disabled");
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByText("Quédate · 2 agentes")).toBeInTheDocument();
    expect(within(dialog).getByText("Lo tiene conectado 1 cliente; 2 agentes usan sus herramientas")).toBeInTheDocument();
    expect(h.success).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(h.setState).toHaveBeenCalledTimes(1);
  });

  it("confirms with the impact in view", async () => {
    h.setState
      .mockResolvedValueOnce({
        ok: false,
        code: "confirm_required",
        impact: {
          affected: [{ partner_id: "p1", partner_name: "Amacrux", clients: [{ tenant_id: "t1", name: "Quédate", connection_status: "connected", agents: 1 }] }],
          totals: { clients: 1, agents: 1 },
        },
      })
      .mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item()]} />);
    await user.selectOptions(screen.getByLabelText("Decisión sobre Tienda para este partner"), "disabled");
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await user.click(await within(dialog).findByRole("button", { name: "Quitar el acceso" }));
    expect(h.setState).toHaveBeenLastCalledWith("tienda", "p1", {
      state: "disabled",
      reason: "Solo para Amacrux",
      confirm: true,
    });
    expect(h.success).toHaveBeenCalled();
  });

  it("explains a partner's default connector instead of saving", async () => {
    h.setState.mockResolvedValue({
      ok: false,
      code: "partner_default_connector",
      partners: [{ id: "p1", name: "Amacrux" }],
    });
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item()]} />);
    await user.selectOptions(screen.getByLabelText("Decisión sobre Tienda para este partner"), "disabled");
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByText(/Es el conector por defecto para dar de alta clientes de Amacrux/)).toBeInTheDocument();
  });

  it("passes axe with the table and with the dialog open on the impact", async () => {
    h.setState.mockResolvedValueOnce({
      ok: false,
      code: "confirm_required",
      impact: {
        affected: [{ partner_id: "p1", partner_name: "Amacrux", clients: [{ tenant_id: "t1", name: "Quédate", connection_status: "connected", agents: 2 }] }],
        totals: { clients: 1, agents: 2 },
      },
    });
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item(), item({ slug: "quedate", display_name: "Quédate", partner_state: "disabled", effective: false })]} />);
    expect(await axeViolations()).toEqual([]);
    await user.selectOptions(screen.getByLabelText("Decisión sobre Tienda para este partner"), "disabled");
    const dialog = await screen.findByRole("dialog");
    expect(await axeViolations()).toEqual([]);
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await within(dialog).findByText("Quédate · 2 agentes");
    expect(await axeViolations()).toEqual([]);
  });

  it("gives focus back to the select that opened the dialog when it closes", async () => {
    const user = userEvent.setup();
    render(<PartnerConnectorsList partnerId="p1" items={[item()]} />);
    const select = screen.getByLabelText("Decisión sobre Tienda para este partner");
    await user.selectOptions(select, "disabled");
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(select).toHaveFocus();
    expect(select).toHaveValue("default");
  });
});
