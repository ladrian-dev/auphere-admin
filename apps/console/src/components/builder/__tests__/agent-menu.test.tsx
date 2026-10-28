import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentHeader } from "@/lib/backend/agent-life-types";

import { AGENTS, CH1, CH2, COBROS, RECEPCION, REF, VENTAS, agent, fail, header, ok } from "./life-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));

const { AgentMenu } = await import("../agent-menu");
type Actions = NonNullable<React.ComponentProps<typeof AgentMenu>["actions"]>;

/**
 * Spec 047 (historias 19 y 20, T124; requisitos 26 a 28) — el ⋯ de la cabecera
 * del agente: solo lo permitido; pausar confirma con las conversaciones en
 * curso; archivar pide el destino de cada número y, si es el agente por
 * defecto, elegir otro antes; renombrar y hacerlo agente por defecto.
 */

function menuWith(h: AgentHeader = header(), actions: Partial<Actions> = {}) {
  const full: Actions = {
    rename: vi.fn(async ({ name }: { name: string }) => ok(agent({ id: COBROS, name }))),
    pause: vi.fn(async () => ok(header({ lifecycle: "paused", visible_state: { code: "paused", tone: "warn", reason: "manual" }, allowed: ["rename", "resume", "archive"] }))),
    resume: vi.fn(async () => ok(header())),
    archive: vi.fn(async () => ok(header({ lifecycle: "archived", visible_state: { code: "archived", tone: "muted", reason: null }, allowed: ["restore"] }))),
    restore: vi.fn(async () => ok(header({ lifecycle: "paused" }))),
    makeDefault: vi.fn(async ({ agent: id }: { agent: string }) => ok(header({ id, name: id === VENTAS ? "Ventas" : "Cobros", is_default: true }))),
    ...actions,
  };
  const onHeader = vi.fn();
  const onArchived = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <AgentMenu refId={REF} header={h} agents={AGENTS} onHeader={onHeader} onArchived={onArchived} actions={full} />
    </LocaleProvider>,
  );
  return { ...view, actions: full, onHeader, onArchived };
}

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Más acciones de Cobros" }));
  return screen.findByRole("menu");
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("el ⋯ del agente", () => {
  it("solo ofrece lo permitido, y nada a quien no puede (§V)", async () => {
    const user = userEvent.setup();
    const { container, unmount } = menuWith();
    const menu = await open(user);
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Renombrar", "Pausar", "Hacer agente por defecto", "Archivar"]);
    expect(await axeViolations(container)).toEqual([]);
    unmount();
    menuWith(header({ allowed: [] }));
    expect(screen.queryByRole("button", { name: "Más acciones de Cobros" })).toBeNull();
  });

  it("pausar sin conversaciones en curso no pregunta, con ellas dice cuántas (27.8)", async () => {
    const user = userEvent.setup();
    const pause = vi
      .fn<Actions["pause"]>()
      .mockResolvedValueOnce(fail(409, "confirm_required", { open_conversations: 3 }))
      .mockResolvedValueOnce(ok(header({ lifecycle: "paused" })));
    const { onHeader } = menuWith(header(), { pause });
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Pausar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Pausar Cobros?" });
    expect(within(dialog).getByText(/Hay 3 conversaciones en curso/)).toBeVisible();
    expect(pause).toHaveBeenLastCalledWith({ ref: REF, agent: COBROS });
    await user.click(within(dialog).getByRole("button", { name: "Pausar igualmente" }));
    expect(pause).toHaveBeenLastCalledWith({ ref: REF, agent: COBROS, confirm: true });
    await waitFor(() => expect(onHeader).toHaveBeenCalledWith(expect.objectContaining({ lifecycle: "paused" })));
    expect(toast.success).toHaveBeenCalledWith("Cobros está en pausa. Los mensajes se guardan y van a la Bandeja.");
  });

  it("reanudar y hacerlo agente por defecto", async () => {
    const user = userEvent.setup();
    const { actions, onHeader } = menuWith(header({ allowed: ["resume", "make_default"] }));
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Reanudar" }));
    expect(actions.resume).toHaveBeenCalledWith({ ref: REF, agent: COBROS });
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Hacer agente por defecto" }));
    expect(actions.makeDefault).toHaveBeenCalledWith({ ref: REF, agent: COBROS });
    await waitFor(() => expect(onHeader).toHaveBeenLastCalledWith(expect.objectContaining({ is_default: true })));
  });

  it("renombra, y un nombre ocupado se dice", async () => {
    const user = userEvent.setup();
    const rename = vi.fn<Actions["rename"]>().mockResolvedValueOnce(fail(409, "name_taken")).mockResolvedValueOnce(ok(agent({ id: COBROS, name: "Pagos" })));
    const { onHeader } = menuWith(header(), { rename });
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Renombrar" }));
    const dialog = await screen.findByRole("dialog", { name: "Renombrar Cobros" });
    const field = within(dialog).getByRole("textbox", { name: /Nombre nuevo/ });
    expect(field).toHaveValue("Cobros");
    await user.clear(field);
    await user.type(field, "Ventas");
    await user.click(within(dialog).getByRole("button", { name: "Guardar el nombre" }));
    expect(await within(dialog).findByText(/Ya hay un agente con ese nombre/)).toBeVisible();
    await user.clear(field);
    await user.type(field, "Pagos");
    await user.click(within(dialog).getByRole("button", { name: "Guardar el nombre" }));
    await waitFor(() => expect(onHeader).toHaveBeenCalledWith(expect.objectContaining({ name: "Pagos" })));
  });

  it("archivar pide quién atiende cada número: otro agente o «Dejar en pausa» (28.1)", async () => {
    const user = userEvent.setup();
    const { actions, onArchived } = menuWith();
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Archivar" }));
    const dialog = await screen.findByRole("dialog", { name: "Archivar Cobros" });
    const first = within(dialog).getByRole("combobox", { name: "Quién atiende +34 600 000 001" });
    expect(within(first).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Quién atiende cada número a partir de ahora",
      "Recepción",
      "Ventas",
      "Dejar en pausa",
    ]);
    await user.click(within(dialog).getByRole("button", { name: "Archivar" }));
    expect(within(dialog).getByText("Elige quién atiende cada número.")).toBeVisible();
    expect(actions.archive).not.toHaveBeenCalled();
    await user.selectOptions(first, VENTAS);
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Quién atiende +34 600 000 002" }), "pause");
    expect(await axeViolations(dialog)).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Archivar" }));
    expect(actions.archive).toHaveBeenCalledWith({
      ref: REF,
      agent: COBROS,
      channels: [
        { channel_id: CH1, to: VENTAS },
        { channel_id: CH2, to: "pause" },
      ],
    });
    await waitFor(() => expect(onArchived).toHaveBeenCalledWith(expect.objectContaining({ lifecycle: "archived" })));
  });

  it("el agente por defecto pide elegir otro antes de archivarlo (28.4)", async () => {
    const user = userEvent.setup();
    const { actions } = menuWith(header({ is_default: true, allowed: ["rename", "pause", "archive"] }));
    await user.click(within(await open(user)).getByRole("menuitem", { name: "Archivar" }));
    const dialog = await screen.findByRole("dialog", { name: "Archivar Cobros" });
    expect(within(dialog).getByText(/Cobros es el agente por defecto/)).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: "Archivar" })).toBeNull();
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Nuevo agente por defecto" }), VENTAS);
    await user.click(within(dialog).getByRole("button", { name: "Cambiar el agente por defecto" }));
    expect(actions.makeDefault).toHaveBeenCalledWith({ ref: REF, agent: VENTAS });
    expect(await within(dialog).findByRole("button", { name: "Archivar" })).toBeVisible();
    expect(within(dialog).getByRole("combobox", { name: "Quién atiende +34 600 000 001" })).toBeVisible();
    expect(RECEPCION).toBeTruthy();
  });
});
