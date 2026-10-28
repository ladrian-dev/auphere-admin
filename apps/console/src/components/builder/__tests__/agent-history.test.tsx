import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { AGENT, HISTORY, REF, ok } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({ historyAction: vi.fn(), restoreVersionAction: vi.fn() }));

const { AgentHistory } = await import("../agent-history");
type Actions = NonNullable<React.ComponentProps<typeof AgentHistory>["actions"]>;

/**
 * Spec 047 (historia 9, T094; requisito 24.2, 24.3) — el historial: número,
 * quién y cuándo, nota, qué cambió, las pruebas y el motivo si se saltó la
 * puerta. «Restaurar» crea un borrador, con confirmación, y solo lo ve quien
 * puede escribir.
 */

function screenWith(props: Partial<React.ComponentProps<typeof AgentHistory>> = {}) {
  const actions: Actions = {
    load: vi.fn(async () => ok(HISTORY)),
    restore: vi.fn(async () => ok({ draft_number: 4, restored_from: 2, revision: 9 })),
  };
  const onRestored = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <AgentHistory refId={REF} agentId={AGENT} history={HISTORY} canWrite onRestored={onRestored} actions={actions} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions, onRestored };
}

const entry = (n: number) => screen.getByRole("listitem", { name: `v${n}` }) as HTMLElement;

describe("el historial (24.2)", () => {
  it("cada versión con su estado, autor, nota, cambios, pruebas y motivo, y pasa axe", async () => {
    const { container } = screenWith();
    const v3 = entry(3);
    expect(within(v3).getByText("Atiende ahora")).toBeVisible();
    expect(within(v3).getByText(/luis@ladrian\.studio ·/)).toBeVisible();
    expect(within(v3).getByText("Respuestas más cortas")).toBeVisible();
    expect(within(v3).getByText("Cambió: Instrucciones, Reglas")).toBeVisible();
    expect(within(v3).getByText("Pruebas: 95 %")).toBeVisible();
    expect(within(v3).getByText(/Guardada saltando la puerta: «El cliente abre mañana/)).toBeVisible();
    expect(within(entry(2)).getByText("Anterior")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Restaurar» solo en las anteriores, con confirmación, y avisa del borrador nuevo (24.3)", async () => {
    const user = userEvent.setup();
    const { actions, onRestored } = screenWith();
    expect(within(entry(3)).queryByRole("button", { name: /Restaurar/ })).toBeNull();
    await user.click(within(entry(2)).getByRole("button", { name: "Restaurar la v2" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Restaurar la v2?" });
    expect(within(dialog).getByText(/Pasará las pruebas antes de llegar a clientes/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Restaurar" }));
    expect(actions.restore).toHaveBeenCalledWith({ ref: REF, agent: AGENT, number: 2 });
    await waitFor(() => expect(onRestored).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("Borrador nuevo con la v2. Guárdalo para que atienda.");
  });

  it("dice cada parte con palabras y no enseña claves internas (recorrido UI)", () => {
    // La v1 de un agente nuevo cambia todo el AgentSpec, también `mode`,
    // `schema_version` y `test_suite`, que salían tal cual. Las partes sin
    // palabra (`partKey`) son del formato: no se enseñan.
    const first = { ...HISTORY[1]!, number: 1, changed: ["identity", "mode", "schema_version", "test_suite", "rules"] };
    screenWith({ history: [first] });
    expect(within(entry(1)).getByText("Cambió: Nombre y descripción, Reglas")).toBeVisible();
    expect(screen.queryByText(/schema_version|test_suite|\bmode\b/)).toBeNull();
  });

  it("quien solo lee no ve «Restaurar»", () => {
    screenWith({ canWrite: false });
    expect(screen.queryByRole("button", { name: /Restaurar/ })).toBeNull();
  });
});
