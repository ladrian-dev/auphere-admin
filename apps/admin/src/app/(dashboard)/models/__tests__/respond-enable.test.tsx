import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";
import type { DeploymentRow } from "@/lib/backend-models";

import { POLICY, row } from "./fixtures";

const h = vi.hoisted(() => ({ enable: vi.fn(), disable: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: vi.fn(),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: vi.fn(),
  putSalePolicyAction: vi.fn(),
  respondEnableAction: (...a: unknown[]) => h.enable(...a),
  respondDisableAction: (...a: unknown[]) => h.disable(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { DeploymentsTable } = await import("../deployments-table");

/**
 * Spec 065 (T074, T075; requisitos 1.3 y 1.4) — Plataforma › Modelos:
 * «Habilitar para responder» con la nota de la pasada de la batería y
 * «Deshabilitar» con el motivo, los dos con confirmación. Cada fila dice si el
 * modelo puede responder a los agentes en este entorno. Un modelo sin perfil de
 * llamada no lo ofrece, y la API de antes (sin los campos) no dice nada.
 */

const NOTE = "2026-11-24 · a1b2c3d · cable 42/42 · real 18/18";

const haiku = (o: Partial<DeploymentRow> & { status?: DeploymentRow["deployment"]["status"] } = {}) => {
  const base = row({ uuid: "haiku", display_name: "Claude Haiku 5.5", has_respond_profile: true, respond_enabled_at: null, ...o });
  return { ...base, deployment: { ...base.deployment, id: "anthropic/claude-haiku-5-5", provider: "anthropic" } };
};
const ENABLED = haiku({
  respond_enabled_at: "2026-11-24T09:30:00Z",
  respond_enabled_by: "operator:luis@auphere.com",
  respond_enabled_note: NOTE,
});

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

function table(rows: DeploymentRow[]) {
  return render(<DeploymentsTable rows={rows} policy={POLICY} routerVisible={false} />);
}

function rowOf(name: string): HTMLElement {
  const found = screen.getAllByRole("row").find((r) => within(r).queryByText(name, { selector: "span" }));
  if (!found) throw new Error(`no row for ${name}`);
  return found;
}

async function menuOf(name: string): Promise<string[]> {
  const trigger = within(rowOf(name)).queryByRole("button", { name: `Más acciones de ${name}` });
  if (!trigger) return [];
  await userEvent.click(trigger);
  const items = await screen.findAllByRole("menuitem");
  const names = items.map((i) => i.textContent ?? "");
  await userEvent.keyboard("{Escape}");
  return names;
}

async function pick(name: string, item: string) {
  await userEvent.click(within(rowOf(name)).getByRole("button", { name: `Más acciones de ${name}` }));
  await userEvent.click(await screen.findByRole("menuitem", { name: item }));
  return screen.findByRole("dialog");
}

describe("lo que dice cada fila", () => {
  it("sin habilitar: lo dice y explica qué falta; habilitado: desde cuándo y con qué pasada", async () => {
    const { container } = table([haiku(), { ...ENABLED, uuid: "sonnet", display_name: "Claude Sonnet 5.5" }]);
    const off = rowOf("Claude Haiku 5.5");
    expect(within(off).getByText("Sin habilitar para responder")).toBeTruthy();
    expect(within(off).getByText("Pasa primero la batería en este entorno.")).toBeTruthy();
    const on = rowOf("Claude Sonnet 5.5");
    expect(within(on).getByText("Habilitado para responder")).toBeTruthy();
    expect(within(on).getByText(`El 24 nov 2026 · ${NOTE}`)).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin perfil de llamada, o con una API que aún no lo dice, nada", async () => {
    table([haiku({ has_respond_profile: false }), row({ uuid: "old", display_name: "Antiguo" })]);
    for (const name of ["Claude Haiku 5.5", "Antiguo"]) {
      expect(within(rowOf(name)).queryByText(/habilitar para responder/i)).toBeNull();
      expect(within(rowOf(name)).queryByText(/Habilitado para responder/)).toBeNull();
      expect(await menuOf(name)).not.toContain("Habilitar para responder");
    }
  });
});

describe("«Habilitar para responder», con la nota de la pasada", () => {
  it("se ofrece en un modelo activo con perfil y sin habilitar, y no en uno sin activar", async () => {
    table([haiku(), haiku({ uuid: "draft", display_name: "Haiku en pruebas", status: "draft" })]);
    const items = await menuOf("Claude Haiku 5.5");
    expect(items).toContain("Habilitar para responder");
    expect(items).not.toContain("Deshabilitar para responder");
    expect(await menuOf("Haiku en pruebas")).not.toContain("Habilitar para responder");
  });

  it("pide la nota, dice qué cambia y habilita con ella", async () => {
    h.enable.mockResolvedValue({ ok: true, data: ENABLED });
    table([haiku()]);
    const dialog = await pick("Claude Haiku 5.5", "Habilitar para responder");
    expect(within(dialog).getByRole("heading", { name: "Habilitar Claude Haiku 5.5 para responder" })).toBeTruthy();
    expect(dialog.textContent).toContain("Vale solo en este entorno.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Habilitar para responder" }));
    expect(within(dialog).getByText("Hace falta la pasada de la batería.")).toBeTruthy();
    expect(h.enable).not.toHaveBeenCalled();
    const note = within(dialog).getByRole("textbox", { name: /Pasada de la batería/ });
    expect(note).toHaveAttribute("placeholder", NOTE);
    await userEvent.type(note, NOTE);
    expect(await axeViolations(dialog)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Habilitar para responder" }));
    expect(h.enable).toHaveBeenCalledWith("haiku", NOTE);
    await waitFor(() => expect(h.success).toHaveBeenCalled());
    expect(h.refresh).toHaveBeenCalled();
  });

  it("un modelo sin perfil de llamada (409) se dice en palabras, sin cerrar", async () => {
    h.enable.mockResolvedValue({ ok: false, code: "no_respond_profile", error: "Este modelo no tiene perfil de llamada: no se puede habilitar para responder." });
    table([haiku()]);
    const dialog = await pick("Claude Haiku 5.5", "Habilitar para responder");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Pasada de la batería/ }), NOTE);
    await userEvent.click(within(dialog).getByRole("button", { name: "Habilitar para responder" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("no tiene perfil de llamada");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});

describe("«Deshabilitar para responder», con el motivo", () => {
  it("es lo último del menú, aparte; dice qué pasa con los agentes y pide el motivo", async () => {
    h.disable.mockResolvedValue({ ok: true, data: haiku() });
    table([{ ...ENABLED, uses: { defaults: [], agents: 2, clients: ["Jemma's Hair Salón"], verified: true, problem: null } }]);
    const items = await menuOf("Claude Haiku 5.5");
    expect(items.at(-1)).toBe("Deshabilitar para responder");
    expect(items).not.toContain("Habilitar para responder");
    const dialog = await pick("Claude Haiku 5.5", "Deshabilitar para responder");
    expect(within(dialog).getByRole("heading", { name: "Deshabilitar Claude Haiku 5.5 para responder" })).toBeTruthy();
    expect(dialog.textContent).toMatch(/pasan al modelo por defecto de Auphere/);
    expect(dialog.textContent).toMatch(/aviso/);
    expect(within(dialog).getByText("Responden con él 2 agentes de Jemma's Hair Salón")).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Deshabilitar" }));
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();
    expect(h.disable).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Falla la batería real");
    expect(await axeViolations(dialog)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Deshabilitar" }));
    expect(h.disable).toHaveBeenCalledWith("haiku", "Falla la batería real");
  });

  it("no se ofrece sobre el modelo por defecto de los agentes ni sobre una reserva", async () => {
    for (const use of ["agent_default", "respond_fallback_openai", "respond_fallback_anthropic"]) {
      const { unmount } = table([{ ...ENABLED, uses: { defaults: [use], agents: 0, clients: [], verified: true, problem: null } }]);
      expect(await menuOf("Claude Haiku 5.5")).not.toContain("Deshabilitar para responder");
      unmount();
    }
  });

  it("el título de los dos diálogos se equilibra y parte un nombre larguísimo (T092, regla 2 del workspace)", async () => {
    const long = "Donaudampfschifffahrtsgesellschaftsmodell";
    for (const [r, item] of [
      [haiku({ display_name: long }), "Habilitar para responder"],
      [{ ...ENABLED, display_name: long }, "Deshabilitar para responder"],
    ] as const) {
      const { unmount } = table([r]);
      const dialog = await pick(long, item);
      const title = within(dialog).getByRole("heading", { name: `${item.split(" ")[0]} ${long} para responder` });
      expect(title.className).toMatch(/text-balance/);
      // `wrap-anywhere`: el diálogo es una rejilla, y con `break-words` la palabra ensancharía la columna.
      expect(title.className).toMatch(/wrap-anywhere/);
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      unmount();
    }
  });

  it("los clientes que responden con él se parten aunque su nombre sea una sola palabra larguísima (T092)", async () => {
    const client = "Donaudampfschifffahrtsgesellschaftskapitänsmützen";
    table([{ ...ENABLED, uses: { defaults: [], agents: 2, clients: [client], verified: true, problem: null } }]);
    const dialog = await pick("Claude Haiku 5.5", "Deshabilitar para responder");
    const callout = within(dialog).getByText(`Responden con él 2 agentes de ${client}`).closest("[data-slot=callout]") as HTMLElement;
    expect(callout.className).toMatch(/wrap-anywhere/);
  });

  it("si la API lo rechaza porque está en uso (409), lo dice en palabras y no cierra", async () => {
    h.disable.mockResolvedValue({
      ok: false,
      code: "model_in_use",
      error: "El modelo está en uso: por defecto para los agentes sin modelo elegido. Por eso no cambia de estado.",
    });
    table([ENABLED]);
    const dialog = await pick("Claude Haiku 5.5", "Deshabilitar para responder");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "x");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deshabilitar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("por defecto para los agentes sin modelo elegido");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});
