import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";
import type { AdminAgentModelRow, RespondDefault } from "@/lib/backend-models";

const h = vi.hoisted(() => ({ save: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../agent-model-actions", () => ({ setAgentModelAction: (...a: unknown[]) => h.save(...a) }));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { AgentModels, AgentModelsSkeleton } = await import("../agent-models");

/**
 * Spec 065 (T074; requisitos 7.1 y 7.2) — Cliente › Agente, «Modelo de cada
 * agente»: con qué modelo responde cada agente y de dónde sale (lo eligió el
 * partner, lo fijó Auphere, lo fija la versión o es el de Auphere). Auphere lo
 * cambia en un diálogo, con motivo obligatorio, entre los modelos habilitados
 * para responder, estén o no en la lista del partner. Y los cinco estados.
 */

const TENANT = "22222222-2222-4222-8222-222222222222";
const RECEPCION = "11111111-1111-4111-8111-000000000001";

const ROWS: AdminAgentModelRow[] = [
  {
    agent_id: RECEPCION,
    name: "Recepción e información",
    lifecycle: "active",
    choice: { model_id: "openai/gpt-5.6-terra", display_name: "Terra", set_by: "operator", set_at: "2026-11-20T10:00:00Z" },
    effective: { model_id: "openai/gpt-5.6-terra", display_name: "Terra", source: "agent_operator" },
  },
  {
    agent_id: "11111111-1111-4111-8111-000000000002",
    name: "Reservas",
    lifecycle: "active",
    choice: null,
    effective: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", source: "platform" },
  },
  {
    agent_id: "11111111-1111-4111-8111-000000000003",
    name: "Ventas",
    lifecycle: "active",
    choice: { model_id: "openai/gpt-5.6-luna", display_name: "Luna", set_by: "partner", set_at: "2026-11-21T09:00:00Z" },
    effective: { model_id: "openai/gpt-5.6-luna", display_name: "Luna", source: "agent" },
  },
  {
    agent_id: "11111111-1111-4111-8111-000000000004",
    name: "Seguimiento",
    lifecycle: "active",
    choice: null,
    effective: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", source: "version" },
  },
];

const RESPOND: RespondDefault = {
  model_id: "openai/gpt-5.6-sol",
  display_name: "Sol",
  set_by: null,
  set_at: null,
  options: [
    { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5" },
    { model_id: "openai/gpt-5.6-luna", display_name: "Luna" },
    { model_id: "openai/gpt-5.6-terra", display_name: "Terra" },
    { model_id: "openai/gpt-5.6-sol", display_name: "Sol" },
  ],
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

function block(over: Partial<React.ComponentProps<typeof AgentModels>> = {}) {
  return render(<AgentModels tenantId={TENANT} rows={ROWS} respond={RESPOND} principalId={RECEPCION} {...over} />);
}

const rowOf = (name: string) => {
  const found = screen.getAllByRole("row").find((r) => within(r).queryByText(name));
  if (!found) throw new Error(`no row for ${name}`);
  return found;
};

async function openChange(name: string) {
  await userEvent.click(within(rowOf(name)).getByRole("button", { name: `Cambiar el modelo de ${name}` }));
  return screen.findByRole("dialog");
}

describe("la lista por agente (7.1)", () => {
  it("dice con qué responde cada agente y de dónde sale; pasa axe", async () => {
    const { container } = block();
    expect(screen.getByRole("heading", { name: "Modelo de cada agente" })).toBeVisible();
    expect(screen.getByText(/esté o no en la lista del partner/)).toBeVisible();
    for (const header of ["Agente", "Responde con", "De dónde sale"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeTruthy();
    }
    const recepcion = rowOf("Recepción e información");
    expect(within(recepcion).getByText("Agente principal")).toBeTruthy();
    expect(within(recepcion).getByText("Terra")).toBeTruthy();
    expect(within(recepcion).getByText("Fijado por Auphere")).toBeTruthy();
    expect(within(recepcion).getByText(/20 nov 2026/)).toBeTruthy();
    expect(within(rowOf("Reservas")).getByText("Por defecto de Auphere")).toBeTruthy();
    expect(within(rowOf("Ventas")).getByText("Elegido por el partner")).toBeTruthy();
    expect(within(rowOf("Seguimiento")).getByText("Lo fija la versión")).toBeTruthy();
    expect(within(rowOf("Reservas")).queryByText("Agente principal")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("si lo elegido no es con lo que responde, lo dice", () => {
    block({
      rows: [
        {
          ...ROWS[2]!,
          choice: { model_id: "anthropic/claude-opus-5-5", display_name: "Claude Opus 5.5", set_by: "partner", set_at: null },
          effective: { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5", source: "platform" },
        },
      ],
    });
    expect(within(rowOf("Ventas")).getByText("Elegido: Claude Opus 5.5 (por el partner)")).toBeTruthy();
  });
});

describe("cambiar el modelo, con motivo (7.2)", () => {
  it("ofrece el de Auphere y los habilitados para responder, con el de ahora marcado", async () => {
    block();
    const dialog = await openChange("Recepción e información");
    expect(within(dialog).getByRole("heading", { name: "Cambiar el modelo de Recepción e información" })).toBeTruthy();
    const select = within(dialog).getByRole("combobox", { name: "Modelo" }) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "Por defecto de Auphere (hoy: Sol)",
      "Claude Haiku 5.5",
      "Luna",
      "Terra",
      "Sol",
    ]);
    expect(select.value).toBe("openai/gpt-5.6-terra");
    expect(within(dialog).getByText(/Solo modelos habilitados para responder en este entorno/)).toBeTruthy();
    expect(await axeViolations(dialog)).toEqual([]);
  });

  it("sin motivo no guarda, y lo dice en el campo", async () => {
    block();
    const dialog = await openChange("Recepción e información");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Modelo" }), "anthropic/claude-haiku-5-5");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el modelo" }));
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();
    expect(within(dialog).getByRole("textbox", { name: /Motivo/ })).toHaveAttribute("aria-invalid", "true");
    expect(h.save).not.toHaveBeenCalled();
  });

  it("guarda el modelo elegido con el motivo, avisa y vuelve a leer", async () => {
    h.save.mockResolvedValue({
      ok: true,
      data: {
        agent_id: RECEPCION,
        choice: null,
        effective: { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5", source: "agent_operator" },
      },
    });
    block();
    const dialog = await openChange("Recepción e información");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Modelo" }), "anthropic/claude-haiku-5-5");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Prueba de Haiku con este cliente");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el modelo" }));
    expect(h.save).toHaveBeenCalledWith(TENANT, RECEPCION, "anthropic/claude-haiku-5-5", "Prueba de Haiku con este cliente");
    await waitFor(() =>
      expect(h.success).toHaveBeenCalledWith("Recepción e información responde con Claude Haiku 5.5 desde su próximo mensaje."),
    );
    expect(h.refresh).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("«Por defecto de Auphere» guarda `null`", async () => {
    h.save.mockResolvedValue({ ok: true, data: { agent_id: RECEPCION, choice: null, effective: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", source: "platform" } } });
    block();
    const dialog = await openChange("Recepción e información");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Modelo" }), "");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Vuelve al de Auphere");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el modelo" }));
    expect(h.save).toHaveBeenCalledWith(TENANT, RECEPCION, null, "Vuelve al de Auphere");
  });

  it("si la API lo rechaza, lo dice en el diálogo y no lo cierra", async () => {
    h.save.mockResolvedValue({
      ok: false,
      code: "unknown_model",
      error: "No se pudo cambiar el modelo: ese modelo ya no está habilitado para responder. Recarga la página y elige otro.",
    });
    block();
    const dialog = await openChange("Ventas");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Modelo" }), "openai/gpt-5.6-terra");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "x");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el modelo" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/ya no está habilitado para responder/);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(h.success).not.toHaveBeenCalled();
  });
});

describe("los cinco estados", () => {
  it("cargando: el esqueleto del bloque, anunciado", () => {
    render(<AgentModelsSkeleton />);
    expect(screen.getByRole("status", { name: "Cargando el modelo de cada agente" })).toBeTruthy();
  });

  it("error al leer: lo dice y deja reintentar", async () => {
    block({ rows: null });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No se pudo leer el modelo de los agentes");
    expect(alert).toHaveTextContent("Los agentes siguen respondiendo como hasta ahora.");
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalled();
  });

  it("vacío: sin agentes activos", () => {
    block({ rows: [] });
    expect(screen.getByText("Este cliente no tiene agentes activos.")).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("parcial: sin los modelos habilitados se ve la lista, pero no se puede cambiar", () => {
    block({ respond: null });
    expect(rowOf("Ventas")).toBeTruthy();
    expect(screen.getByText(/No se pudieron leer los modelos habilitados para responder/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Cambiar el modelo de/ })).toBeNull();
  });

  it("un nombre larguísimo se parte sin desbordar", () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänsassistenzagent";
    block({ rows: [{ ...ROWS[1]!, name: long }] });
    const name = screen.getByText(long);
    expect(name.className).toMatch(/break-words|wrap-anywhere/);
    expect(name.className).toMatch(/min-w-0/);
  });

  it("los títulos se equilibran, y el del diálogo parte un nombre larguísimo (T092, regla 2 del workspace)", async () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänsassistenzagent";
    block({ rows: [{ ...ROWS[1]!, name: long }] });
    expect(screen.getByRole("heading", { name: "Modelo de cada agente" }).className).toMatch(/text-balance/);
    const dialog = await openChange(long);
    const title = within(dialog).getByRole("heading", { name: `Cambiar el modelo de ${long}` });
    expect(title.className).toMatch(/text-balance/);
    // `wrap-anywhere`: el diálogo es una rejilla, y con `break-words` la palabra ensancharía la columna.
    expect(title.className).toMatch(/wrap-anywhere/);
  });
});
