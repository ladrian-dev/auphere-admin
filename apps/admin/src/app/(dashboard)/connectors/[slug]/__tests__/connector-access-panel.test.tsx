import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "@nexus/ui/test/axe";

import type { ConnectorAccess } from "@/lib/backend-connector-access";

/** Spec 060, T044: el bloque «Disponible para» de la ficha del conector (requisito 3). */
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

const { ConnectorAccessPanel } = await import("../connector-access-panel");

const PARTNERS = [
  { id: "amacrux", name: "Amacrux" },
  { id: "facelad", name: "Facelad" },
];

function access(o: Partial<ConnectorAccess> = {}): ConnectorAccess {
  return {
    slug: "quedate",
    default_enabled: true,
    default_reason: null,
    default_updated_by: null,
    default_updated_at: null,
    partners: [],
    partners_without_decision: 2,
    clients_without_partner_connected: 0,
    ...o,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  h.setDefault.mockResolvedValue({ ok: true });
  h.setState.mockResolvedValue({ ok: true });
});

describe("ConnectorAccessPanel", () => {
  it("says the default and that nobody has a decision yet", () => {
    render(<ConnectorAccessPanel slug="quedate" name="Quédate" access={access()} partners={PARTNERS} />);
    expect(screen.getByText("Por defecto, disponible para todos los partners")).toBeInTheDocument();
    expect(screen.getByText("Ningún partner tiene una decisión propia sobre este conector.")).toBeInTheDocument();
  });

  it("turns the default off with a reason", async () => {
    const user = userEvent.setup();
    render(<ConnectorAccessPanel slug="quedate" name="Quédate" access={access()} partners={PARTNERS} />);
    await user.selectOptions(screen.getByLabelText("Valor por defecto"), "disabled");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/tampoco los que se den de alta después/)).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox"), "Solo para Amacrux");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(h.setDefault).toHaveBeenCalledWith("quedate", {
      enabled: false,
      reason: "Solo para Amacrux",
      confirm: false,
    });
    expect(h.refresh).toHaveBeenCalled();
  });

  it("adds a decision for one partner, the same one the partner's tab writes", async () => {
    const user = userEvent.setup();
    render(
      <ConnectorAccessPanel
        slug="quedate"
        name="Quédate"
        access={access({ default_enabled: false })}
        partners={PARTNERS}
      />,
    );
    await user.selectOptions(screen.getByLabelText("Decidir para un partner"), "amacrux");
    expect(screen.getByLabelText("Para sus clientes")).toHaveValue("enabled");
    await user.click(screen.getByRole("button", { name: "Añadir decisión" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Conector propio");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(h.setState).toHaveBeenCalledWith("quedate", "amacrux", {
      state: "enabled",
      reason: "Conector propio",
      confirm: false,
    });
  });

  it("lists the partners with a decision and lets you return one to the default", async () => {
    const user = userEvent.setup();
    render(
      <ConnectorAccessPanel
        slug="quedate"
        name="Quédate"
        access={access({
          default_enabled: false,
          partners_without_decision: 1,
          partners: [
            {
              partner_id: "amacrux",
              name: "Amacrux",
              state: "enabled",
              effective: true,
              connected_clients: 1,
              set_by: "operator:x",
              set_at: "2026-11-13T10:00:00Z",
              reason: "Conector propio",
            },
          ],
        })}
        partners={PARTNERS}
      />,
    );
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("Disponible")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("1 cliente")).toBeInTheDocument();
    // Solo se ofrece decidir para quien no tiene decisión.
    expect(within(screen.getByLabelText("Decidir para un partner")).queryByText("Amacrux")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Decisión para Amacrux"), "default");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Este partner volverá a seguir el valor por defecto.")).toBeInTheDocument();
  });

  it("passes axe with partner decisions listed and with the dialog open", async () => {
    const user = userEvent.setup();
    render(
      <ConnectorAccessPanel
        slug="quedate"
        name="Quédate"
        access={access({
          default_enabled: false,
          partners_without_decision: 1,
          partners: [
            {
              partner_id: "amacrux",
              name: "Amacrux",
              state: "enabled",
              effective: true,
              connected_clients: 1,
              set_by: "operator:x",
              set_at: "2026-11-13T10:00:00Z",
              reason: "Conector propio",
            },
          ],
        })}
        partners={PARTNERS}
      />,
    );
    expect(await axeViolations()).toEqual([]);
    await user.selectOptions(screen.getByLabelText("Valor por defecto"), "enabled");
    await screen.findByRole("dialog");
    expect(await axeViolations()).toEqual([]);
  });

  it("keeps focus on the block when saving removes the row that opened the dialog", async () => {
    const user = userEvent.setup();
    const decided = access({
      default_enabled: false,
      partners_without_decision: 1,
      partners: [
        {
          partner_id: "amacrux",
          name: "Amacrux",
          state: "enabled",
          effective: true,
          connected_clients: 0,
          set_by: "operator:x",
          set_at: "2026-11-13T10:00:00Z",
          reason: "Conector propio",
        },
      ],
    });
    const view = render(<ConnectorAccessPanel slug="quedate" name="Quédate" access={decided} partners={PARTNERS} />);
    await user.selectOptions(screen.getByLabelText("Decisión para Amacrux"), "default");
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Vuelve al defecto");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // El refresco trae los datos sin la fila.
    view.rerender(
      <ConnectorAccessPanel
        slug="quedate"
        name="Quédate"
        access={access({ default_enabled: false, partners_without_decision: 2 })}
        partners={PARTNERS}
      />,
    );
    expect(screen.queryByLabelText("Decisión para Amacrux")).toBeNull();
    expect(screen.getByLabelText("Valor por defecto")).toHaveFocus();
  });
});
