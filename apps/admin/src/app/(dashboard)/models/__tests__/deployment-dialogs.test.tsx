import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRow } from "@/lib/backend-models";

const h = vi.hoisted(() => ({
  activate: vi.fn(),
  retire: vi.fn(),
  create: vi.fn(),
  unavailable: vi.fn(),
  price: vi.fn(),
  success: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../actions", () => ({
  activateAction: (...a: unknown[]) => h.activate(...a),
  retireAction: (...a: unknown[]) => h.retire(...a),
  createDeploymentAction: (...a: unknown[]) => h.create(...a),
  unavailableAction: (...a: unknown[]) => h.unavailable(...a),
  addPriceAction: (...a: unknown[]) => h.price(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { ActivateDialog, NewDeploymentDialog, RetireDialog, UnavailableDialog } = await import(
  "../deployment-dialogs"
);
const { DeploymentsTable } = await import("../deployments-table");

function row(o: Partial<DeploymentRow> = {}, status: DeploymentRow["deployment"]["status"] = "draft"): DeploymentRow {
  return {
    uuid: "d1",
    display_name: "Haiku UE",
    deployment: {
      id: "bedrock/eu.haiku",
      model: "haiku",
      family: "anthropic-claude",
      provider: "aws_bedrock",
      route: "eu.haiku",
      region: "eu-south-2",
      residency: "eu",
      retention: { zero: false, how: "data_retention_mode:none" },
      license: null,
      contract: { dpa: false, subprocessor_listed: false },
      status,
      retire_after: null,
      quota: { tpm: null, rpm: null, verified_at: null },
      capabilities: {},
      prices: [],
      meter_weights: { w_in: null, w_cache: null, w_out: null },
    },
    current_price: null,
    certified_tasks: [],
    activation_missing: ["subprocessor_not_listed"],
    activation_messages: {
      subprocessor_not_listed: "El proveedor no está dado de alta como subprocesador.",
    },
    ...o,
  };
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

const open = async (name: string) => userEvent.click(screen.getByRole("button", { name }));

/** The refusal of the API: an alert of its own, apart from the gate's callout. */
function alertWith(dialog: HTMLElement, text: string): HTMLElement {
  const found = within(dialog)
    .getAllByRole("alert")
    .find((el) => el.textContent?.includes(text));
  if (!found) throw new Error(`no alert says «${text}»`);
  return found;
}

/** Spec 047 (T150): the catalog's writes, each with its reason. */
describe("the catalog dialogs", () => {
  it("activation says beforehand what is missing and refuses without a reason", async () => {
    render(<ActivateDialog row={row()} />);
    await open("Activar");
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/no está dado de alta como subprocesador/)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar" }));
    expect(h.activate).not.toHaveBeenCalled();
    expect(alertWith(dialog, "Hace falta el motivo")).toBeTruthy();
  });

  it("activation shows everything the gate says is missing", async () => {
    h.activate.mockResolvedValue({
      ok: false,
      error: "No se puede activar todavía.",
      code: "activation_rejected",
      missing: { unweighted: "Faltan los pesos del medidor por carril." },
    });
    render(<ActivateDialog row={row()} />);
    await open("Activar");
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "DPA firmado");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar" }));
    expect(h.activate).toHaveBeenCalledWith("d1", "DPA firmado");
    const alert = alertWith(dialog, "No se puede activar todavía.");
    expect(alert.textContent).toContain("Faltan los pesos del medidor");
  });

  it("a retirement shows the substitute proposed to each fixed agent", async () => {
    h.retire.mockResolvedValue({
      ok: true,
      data: {
        deployment: row({}, "retiring"),
        proposals: [
          { tenant_id: "t1", agent_id: "a1", client_ref: "barberia-1", agent: "Reservas", proposed: "prov/near" },
          { tenant_id: "t1", agent_id: "a2", client_ref: "barberia-1", agent: "Ventas", proposed: "auto" },
        ],
      },
    });
    render(<RetireDialog row={row({}, "active")} />);
    await open("Retirar");
    const dialog = screen.getByRole("dialog");
    const date = dialog.querySelector('input[type="date"]') as HTMLInputElement;
    await userEvent.type(date, "2026-12-01");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Lo retira el proveedor");
    await userEvent.click(within(dialog).getByRole("button", { name: "Registrar la retirada" }));
    expect(h.retire).toHaveBeenCalledWith("d1", {
      retire_after: "2026-12-01T00:00:00+00:00",
      reason: "Lo retira el proveedor",
    });
    const status = within(dialog).getByRole("status");
    expect(status.textContent).toContain("prov/near");
    expect(status.textContent).toContain("«Automático»");
  });

  it("«No disponible» is a destructive write with its reason", async () => {
    h.unavailable.mockResolvedValue({ ok: true, data: row({}, "unavailable") });
    render(<UnavailableDialog row={row({}, "active")} />);
    await open("No disponible");
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Rompió el DPA");
    await userEvent.click(within(dialog).getByRole("button", { name: "Marcar no disponible" }));
    expect(h.unavailable).toHaveBeenCalledWith("d1", "Rompió el DPA");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("a new deployment is validated before it leaves, and goes as a draft", async () => {
    h.create.mockResolvedValue({ ok: true, data: row() });
    render(<NewDeploymentDialog />);
    await open("Nuevo despliegue");
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Dar de alta" }));
    expect(h.create).not.toHaveBeenCalled();
    expect(within(dialog).getAllByText("Hace falta un nombre.").length).toBe(1);

    await userEvent.type(within(dialog).getByRole("textbox", { name: /^Clave/ }), "scaleway/gpt-oss-20b");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /^Nombre/ }), "gpt-oss-20b");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /^Modelo/ }), "gpt-oss-20b");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /^Proveedor/ }), "scaleway");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Candidato a clasificar");
    await userEvent.click(within(dialog).getByRole("button", { name: "Dar de alta" }));
    expect(h.create).toHaveBeenCalledTimes(1);
    const [body] = h.create.mock.calls[0] as [Record<string, unknown>];
    expect(body.id).toBe("scaleway/gpt-oss-20b");
    expect(body.residency).toBe("eu");
    expect(body.retention).toEqual({ zero: false, how: null });
  });
});

describe("the catalog table", () => {
  it("says what each deployment lacks and offers only the writes that apply", () => {
    render(
      <DeploymentsTable
        rows={[
          row(),
          row(
            {
              uuid: "d2",
              display_name: "Activo",
              activation_missing: [],
              activation_messages: {},
              certified_tasks: ["answer", "classify"],
            },
            "active",
          ),
        ]}
      />,
    );
    const [, draft, active] = screen.getAllByRole("row");
    expect(within(draft!).getByText(/subprocesador/)).toBeTruthy();
    expect(within(draft!).getByRole("button", { name: "Activar" })).toBeTruthy();
    expect(within(draft!).queryByRole("button", { name: "Retirar" })).toBeNull();
    expect(within(active!).queryByRole("button", { name: "Activar" })).toBeNull();
    expect(within(active!).getByRole("button", { name: "Retirar" })).toBeTruthy();
    expect(within(active!).getByText("classify")).toBeTruthy();
    expect(within(active!).getByText("Nada")).toBeTruthy();
  });

  it("has an empty state", () => {
    render(<DeploymentsTable rows={[]} />);
    expect(screen.getByText("Ningún despliegue con este estado")).toBeTruthy();
  });
});
