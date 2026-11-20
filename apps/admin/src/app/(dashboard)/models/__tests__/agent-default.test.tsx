import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";
import type { RespondDefault, RespondDefaultAffected } from "@/lib/backend-models";

const h = vi.hoisted(() => ({ preview: vi.fn(), confirm: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  previewRespondDefaultAction: (...a: unknown[]) => h.preview(...a),
  confirmRespondDefaultAction: (...a: unknown[]) => h.confirm(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { AgentDefaultCard, AgentDefaultSkeleton } = await import("../agent-default");

/**
 * Spec 065 (T078; requisitos 13.1 a 13.6) — Plataforma › Modelos: el modelo con
 * el que responden los agentes sin modelo elegido. El selector solo tiene los
 * habilitados para responder. Antes de cambiarlo se ve qué agentes cambian
 * (la API los da con `409 confirm_required`), se escribe el motivo y se
 * confirma. A los partners no se les avisa. Y los cinco estados.
 */

const SOL = { model_id: "openai/gpt-5.6-sol", display_name: "Sol" };
const HAIKU = { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5" };
const DATA: RespondDefault = {
  ...SOL,
  set_by: null,
  set_at: null,
  options: [HAIKU, { model_id: "openai/gpt-5.6-luna", display_name: "Luna" }, { model_id: "openai/gpt-5.6-terra", display_name: "Terra" }, SOL],
};

const AFFECTED: RespondDefaultAffected[] = [
  { tenant_id: "t1", external_client_ref: "flor-y-encanto", agent_id: "a1", agent_name: "Recepción", current_model: SOL.model_id },
  { tenant_id: "t1", external_client_ref: "flor-y-encanto", agent_id: "a2", agent_name: "Reservas", current_model: SOL.model_id },
  { tenant_id: "t2", external_client_ref: null, agent_id: "a3", agent_name: "Atención", current_model: "openai/gpt-4o" },
];

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

const card = (data: RespondDefault | null = DATA) => render(<AgentDefaultCard data={data} />);
const select = () => screen.getByRole("combobox", { name: "Modelo" }) as HTMLSelectElement;

async function review(model = HAIKU.model_id) {
  await userEvent.selectOptions(select(), model);
  await userEvent.click(screen.getByRole("button", { name: "Revisar el cambio" }));
}

describe("el modelo por defecto de los agentes (13.1)", () => {
  it("dice cuál es y ofrece solo los habilitados para responder; pasa axe", async () => {
    const { container } = card();
    expect(screen.getByRole("heading", { name: "Modelo por defecto de los agentes" })).toBeTruthy();
    expect(screen.getByText("Agentes sin modelo elegido")).toBeTruthy();
    expect(screen.getByText(/No mueve los modelos de la plataforma/)).toBeTruthy();
    expect([...select().options].map((o) => o.textContent)).toEqual(["Claude Haiku 5.5", "Luna", "Terra", "Sol"]);
    expect(select().value).toBe(SOL.model_id);
    expect(screen.getByText(/Ahora: Sol\./)).toBeTruthy();
    expect(screen.getByText(/Solo se pueden elegir modelos habilitados para responder/)).toBeTruthy();
    // Sin otro elegido, no hay nada que revisar.
    expect(screen.getByRole("button", { name: "Revisar el cambio" })).toBeDisabled();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("dice quién lo cambió y cuándo", () => {
    card({ ...DATA, ...HAIKU, set_by: "operator:luis@auphere.com", set_at: "2026-11-24T10:00:00Z" });
    expect(screen.getByText(/Ahora: Claude Haiku 5\.5, lo cambió luis@auphere\.com el 24 nov 2026\./)).toBeTruthy();
  });
});

describe("cambiarlo: la lista de afectados, el motivo y la confirmación (13.2)", () => {
  it("enseña los agentes que cambian por cliente, pide el motivo y confirma; sin aviso a los partners", async () => {
    h.preview.mockResolvedValue({ ok: true, data: { affected: AFFECTED } });
    h.confirm.mockResolvedValue({ ok: true, data: { ...DATA, ...HAIKU } });
    card();
    await review();
    expect(h.preview).toHaveBeenCalledWith(HAIKU.model_id);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Cambiar el modelo por defecto a Claude Haiku 5.5" })).toBeTruthy();
    expect(dialog.textContent).toMatch(/Los partners no reciben ningún aviso/);
    expect(within(dialog).getByText("Cambian 3 agentes de 2 clientes")).toBeTruthy();
    const flor = within(dialog).getByRole("group", { name: "flor-y-encanto" });
    expect(within(flor).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Recepción · ahora Sol", "Reservas · ahora Sol"]);
    // Sin referencia del partner, el cliente es directo; un modelo sin nombre se dice por su id.
    const direct = within(dialog).getByRole("group", { name: "Cliente directo" });
    expect(within(direct).getByText("Atención · ahora openai/gpt-4o")).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cambiar a Claude Haiku 5.5" }));
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();
    expect(h.confirm).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Haiku pasó la batería");
    expect(await axeViolations(dialog)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cambiar a Claude Haiku 5.5" }));
    expect(h.confirm).toHaveBeenCalledWith(HAIKU.model_id, "Haiku pasó la batería");
    await waitFor(() => expect(h.success).toHaveBeenCalledWith("Cambiar el modelo por defecto a Claude Haiku 5.5"));
    expect(h.refresh).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("sin agentes afectados lo dice: solo nacen con él los nuevos", async () => {
    h.preview.mockResolvedValue({ ok: true, data: { affected: [] } });
    card();
    await review();
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toMatch(/No cambia ningún agente ahora: todos tienen un modelo elegido\. Los agentes nuevos nacerán con Claude Haiku 5\.5\./);
    expect(within(dialog).queryByText(/^Cambian /)).toBeNull();
  });

  it("si la revisión falla, lo dice junto al selector y no abre nada", async () => {
    h.preview.mockResolvedValue({ ok: false, code: "unknown_model", error: "Ese modelo no está habilitado para responder en este entorno. Recarga la página y elige otro." });
    card();
    await review();
    expect(await screen.findByRole("alert")).toHaveTextContent(/no está habilitado para responder/);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("si la confirmación falla, lo dice en el diálogo y no lo cierra", async () => {
    h.preview.mockResolvedValue({ ok: true, data: { affected: AFFECTED } });
    h.confirm.mockResolvedValue({ ok: false, error: "La API respondió 500." });
    card();
    await review();
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "x");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cambiar a Claude Haiku 5.5" }));
    await waitFor(() => expect(within(dialog).getAllByRole("alert").some((a) => a.textContent?.includes("La API respondió 500."))).toBe(true));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(h.success).not.toHaveBeenCalled();
  });
});

describe("los cinco estados", () => {
  it("cargando", () => {
    render(<AgentDefaultSkeleton />);
    expect(screen.getByRole("status", { name: "Cargando el modelo por defecto" })).toBeTruthy();
  });

  it("error al leer, con «Reintentar»", async () => {
    card(null);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No se pudo leer el modelo por defecto");
    expect(alert).toHaveTextContent("Los agentes siguen respondiendo como hasta ahora.");
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalled();
  });

  it("vacío: ningún modelo habilitado para responder", () => {
    card({ ...DATA, options: [] });
    expect(screen.getByText(/Ningún modelo está habilitado para responder en este entorno/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Revisar el cambio" })).toBeNull();
  });

  it("parcial: solo está habilitado el de ahora", () => {
    card({ ...DATA, options: [SOL] });
    expect(screen.getByText(/No hay otro modelo habilitado al que cambiar/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revisar el cambio" })).toBeDisabled();
  });
});

/** T092 (gates del workspace): títulos equilibrados y textos largos que se parten a 360 px. */
describe("textos largos", () => {
  // Un correo sin espacios: a 360 px no cabe en la línea, y sin partirse desborda la tarjeta.
  const EMAIL = "operator:luis.adrian.matos.gonzalez.operaciones@auphere-agency-consulting.com";

  // `wrap-anywhere` y no `break-words`: este último no rebaja el ancho mínimo, y dentro de una rejilla
  // (la página, el diálogo) una palabra larga ensancha la columna en vez de partirse.
  it("el correo de quien lo cambió se parte, con modelos y sin ellos", () => {
    const { unmount } = card({ ...DATA, set_by: EMAIL, set_at: "2026-11-24T10:00:00Z" });
    expect(screen.getByText(/lo cambió luis\.adrian/).className).toMatch(/wrap-anywhere/);
    unmount();
    card({ ...DATA, set_by: EMAIL, set_at: "2026-11-24T10:00:00Z", options: [] });
    expect(screen.getByText(/lo cambió luis\.adrian/).className).toMatch(/wrap-anywhere/);
  });

  it("los títulos se equilibran, y el del diálogo parte un nombre larguísimo", async () => {
    const long = { model_id: "x/long", display_name: "Donaudampfschifffahrtsgesellschaftsmodell" };
    h.preview.mockResolvedValue({ ok: true, data: { affected: AFFECTED } });
    card({ ...DATA, options: [...DATA.options, long] });
    expect(screen.getByRole("heading", { name: "Modelo por defecto de los agentes" }).className).toMatch(/text-balance/);
    await review(long.model_id);
    const dialog = await screen.findByRole("dialog");
    const title = within(dialog).getByRole("heading", { name: `Cambiar el modelo por defecto a ${long.display_name}` });
    expect(title.className).toMatch(/text-balance/);
    expect(title.className).toMatch(/wrap-anywhere/);
  });

  it("en el diálogo, la referencia del cliente y el nombre del agente se parten", async () => {
    const ref = "donaudampfschifffahrtsgesellschaftskapitaensmuetzen";
    const agent = "Donaudampfschifffahrtsgesellschaftskapitänsassistenzagent";
    h.preview.mockResolvedValue({ ok: true, data: { affected: [{ ...AFFECTED[0]!, external_client_ref: ref, agent_name: agent }] } });
    card();
    await review();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(ref).className).toMatch(/wrap-anywhere/);
    expect(within(dialog).getByText(`${agent} · ahora Sol`).className).toMatch(/wrap-anywhere/);
  });
});
