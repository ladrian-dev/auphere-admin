import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentAgenda } from "@/lib/backend/agenda-types";

import { AGENDA, AGENDA_TOOLS, ON } from "./agenda-fixtures";
import { AGENT, REF, fail, ok } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/agenda-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));

const { AgendaRow } = await import("../agenda-row");
type Actions = import("../agenda-row").AgendaActions;

/**
 * Spec 057 (historia 3; T029; requisitos 2.1–2.5, 3.5 y 4.4) — «Agenda
 * (Reservas)», la primera fila de Conectores. No es un conector: no se conecta ni
 * tiene permiso. Sus cinco estados: cargando (una fila de esqueleto con su forma),
 * vacío (Reservas no se ofrece: no hay fila), error (con «Reintentar»), parcial
 * (Reservas encendido pero sin terminar: «La agenda aún no está lista» y qué
 * falta) e ideal (activa o no, con «Activar» o «Desactivar»).
 */

function row(agenda: AgentAgenda | null | undefined, over: Partial<Actions> = {}, props: Partial<React.ComponentProps<typeof AgendaRow>> = {}) {
  const actions: Actions = {
    load: vi.fn(async () => ok(AGENDA)),
    set: vi.fn(async ({ enabled }) => ok({ ...AGENDA, draft: { on: enabled, tools_on: enabled ? 9 : 0 }, state: enabled ? ("prepared" as const) : ("none" as const) })),
    tools: vi.fn(async () => ok(AGENDA_TOOLS)),
    setTool: vi.fn(async () => ok({ key: "reservas.join_waitlist", kind: "tool", enabled: false } as never)),
    ...over,
  };
  const onChanged = vi.fn();
  const onAgenda = vi.fn();
  const onProposal = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <ul aria-label="Conectores para este agente">
        <AgendaRow
          refId={REF}
          agentId={AGENT}
          canWrite
          agenda={agenda}
          clientName="Barbería Cultor"
          actions={actions}
          onChanged={onChanged}
          onAgenda={onAgenda}
          onProposal={onProposal}
          wait={() => new Promise((resolve) => setTimeout(resolve, 0))}
          {...props}
        />
      </ul>
    </LocaleProvider>,
  );
  return { ...view, actions, onChanged, onAgenda, onProposal };
}

const agendaRow = () => document.querySelector("[data-slot=agenda-row]") as HTMLElement;

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("la fila de la agenda · sus estados", () => {
  it("cargando: una fila de esqueleto con su forma, dicha; después, la fila", async () => {
    let answer: (value: Awaited<ReturnType<Actions["load"]>>) => void = () => undefined;
    const load = vi.fn<Actions["load"]>(() => new Promise((resolve) => (answer = resolve)));
    row(undefined, { load });
    expect(agendaRow()).toHaveAttribute("data-state", "loading");
    expect(within(agendaRow()).getByRole("status")).toHaveTextContent("Cargando la agenda…");
    await act(async () => answer(ok(AGENDA)));
    expect(within(agendaRow()).getByRole("heading", { level: 3, name: "Agenda (Reservas)" })).toBeVisible();
    expect(load).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
  });

  it("vacío: si Reservas no se ofrece, no hay fila ni botón apagado (§V)", () => {
    row({ ...AGENDA, offered: false });
    expect(agendaRow()).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("error: lo dice, sin inventar el estado, y «Reintentar» la lee otra vez", async () => {
    const user = userEvent.setup();
    const { actions } = row(null);
    expect(agendaRow()).toHaveAttribute("data-state", "error");
    expect(within(agendaRow()).getByText("No se pudo leer la agenda de este agente. Lo que ya hace sigue funcionando.")).toBeVisible();
    expect(within(agendaRow()).queryByRole("button", { name: /Activar/ })).toBeNull();
    await user.click(within(agendaRow()).getByRole("button", { name: "Reintentar" }));
    expect(actions.load).toHaveBeenCalledTimes(1);
    expect(await within(agendaRow()).findByRole("button", { name: "Activar la agenda en este agente" })).toBeVisible();
  });

  it("parcial: Reservas encendido sin terminar dice «La agenda aún no está lista», qué falta y dónde; pasa axe", async () => {
    const { container } = row({ ...ON, ready: false, missing: ["hours_missing", "no_staff", "no_services"] });
    expect(agendaRow()).toHaveAttribute("data-state", "partial");
    const notice = within(agendaRow()).getByText("La agenda aún no está lista").closest("[data-slot=agenda-not-ready]") as HTMLElement;
    expect(within(notice).getByText("Falta el horario del negocio.")).toBeVisible();
    expect(within(notice).getByRole("link", { name: "Ir a Horario" })).toHaveAttribute("href", `/clients/${REF}/business#business-hours`);
    expect(within(notice).getByText("Nadie del equipo está dado de alta en Reservas.")).toBeVisible();
    expect(within(notice).getByText("Lo completa el cliente en Reservas, en Ajustes.")).toBeVisible();
    expect(within(notice).getByRole("link", { name: "Ir a Servicios" })).toHaveAttribute("href", `/clients/${REF}/business#business-services`);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("ideal: es la agenda, no un conector; su ancla es `#agenda`; activa o no, dicho; pasa axe", async () => {
    const { container, unmount } = row(AGENDA);
    expect(agendaRow()).toHaveAttribute("id", "agenda");
    expect(agendaRow()).toHaveAttribute("data-state", "ideal");
    expect(within(agendaRow()).getByText(/Sin activar en este agente/)).toBeVisible();
    expect(within(agendaRow()).queryByRole("button", { name: /Conectar/ })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    unmount();
    row(ON);
    expect(within(agendaRow()).getByText("Activa")).toBeVisible();
    expect(within(agendaRow()).getByText(/9 de 9 herramientas encendidas/)).toBeVisible();
    expect(within(agendaRow()).getByRole("button", { name: "Desactivar la agenda en este agente" })).toBeVisible();
  });
});

describe("la fila de la agenda · activar y desactivar (2.2, 2.3, 2.5)", () => {
  it("con Reservas encendido, «Activar» la pone en el borrador, dice que rige al publicar y sigue la propuesta hasta que llega", async () => {
    const user = userEvent.setup();
    const set = vi.fn<Actions["set"]>(async () => ok({ ...AGENDA, draft: { on: true, tools_on: 9 }, state: "prepared", job: { id: "j1", status: "running" } }));
    const load = vi.fn<Actions["load"]>(async () => ok({ ...AGENDA, draft: { on: true, tools_on: 9 }, state: "prepared", proposal: { id: "p1", status: "open" } }));
    const { onChanged, onAgenda, onProposal } = row(AGENDA, { set, load });
    await user.click(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" }));
    expect(set).toHaveBeenCalledWith({ ref: REF, agent: AGENT, enabled: true });
    expect(toast.success).toHaveBeenCalledWith("Agenda activada en el borrador. Rige al publicar.");
    expect(onChanged).toHaveBeenCalled();
    expect(within(agendaRow()).getByText("Activa en el borrador. Rige al publicar.", { exact: false })).toBeVisible();
    expect(await within(agendaRow()).findByText("Hay una propuesta para su texto de citas.")).toBeVisible();
    expect(load).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
    // Llegó la propuesta: la pantalla vuelve a leer el borrador y sus propuestas.
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    expect(onAgenda).toHaveBeenLastCalledWith(expect.objectContaining({ proposal: { id: "p1", status: "open" } }));
    await user.click(within(agendaRow()).getByRole("button", { name: "Ver la propuesta" }));
    expect(onProposal).toHaveBeenCalled();
  });

  it("con Reservas apagado, pide confirmación para todo el cliente y el modo sugerido ya elegido", async () => {
    const user = userEvent.setup();
    const off: AgentAgenda = {
      ...AGENDA,
      module: { on: false, mode: null, capacity_kind: null },
      ready: false,
      missing: ["reservas_off"],
      suggested: { mode: "capacity", capacity_kind: "restaurant" },
    };
    const { actions } = row(off);
    // Apagado no es «sin terminar»: dice que está apagado, sin la lista de lo que falta.
    expect(agendaRow()).toHaveAttribute("data-state", "ideal");
    expect(within(agendaRow()).getByText(/Reservas está apagado para este cliente/)).toBeVisible();
    await user.click(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Encender Reservas para Barbería Cultor?" });
    expect(dialog).toHaveTextContent("Reservas se enciende para todo el cliente, no solo para este agente.");
    expect(within(dialog).getByRole("radio", { name: /Aforo/ })).toBeChecked();
    expect(within(dialog).getByRole("combobox", { name: "Tipo de negocio" })).toHaveValue("restaurant");
    expect(actions.set).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Encender y activar" }));
    expect(actions.set).toHaveBeenCalledWith({ ref: REF, agent: AGENT, enabled: true, reservas: { mode: "capacity", capacity_kind: "restaurant" } });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("un error al encender se dice en la confirmación, que se queda abierta", async () => {
    const user = userEvent.setup();
    const off: AgentAgenda = { ...AGENDA, module: { on: false, mode: null, capacity_kind: null }, ready: false, missing: ["reservas_off"] };
    row(off, { set: vi.fn(async () => fail(409, "archived")) });
    await user.click(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Encender y activar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("El cliente está archivado, así que no se le puede encender Reservas.");
  });

  it("«Desactivar» la quita del borrador sin preguntar y dice que las citas ya dadas siguen", async () => {
    const user = userEvent.setup();
    const { actions } = row(ON);
    await user.click(within(agendaRow()).getByRole("button", { name: "Desactivar la agenda en este agente" }));
    expect(actions.set).toHaveBeenCalledWith({ ref: REF, agent: AGENT, enabled: false });
    expect(toast.success).toHaveBeenCalledWith("Agenda quitada del borrador. Las citas ya dadas siguen en Reservas. Rige al publicar.");
  });

  it("pasar del máximo de herramientas lo dice con el máximo, y no cambia nada", async () => {
    const user = userEvent.setup();
    row(AGENDA, { set: vi.fn(async () => fail(422, "too_many_tools", { max: 60 })) });
    await user.click(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" }));
    expect(await within(agendaRow()).findByRole("alert")).toHaveTextContent(
      "Con la agenda, este agente pasaría de 60 herramientas, que es el máximo. Apaga alguna antes de activarla.",
    );
    expect(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" })).toBeVisible();
  });

  it("sin partida de construcción, las herramientas cambian y lo dice", async () => {
    const user = userEvent.setup();
    row(AGENDA, { set: vi.fn(async () => ok({ ...AGENDA, draft: { on: true, tools_on: 9 }, state: "prepared" as const, proposal_reason: "build_budget_exhausted" as const })) });
    await user.click(within(agendaRow()).getByRole("button", { name: "Activar la agenda en este agente" }));
    expect(await within(agendaRow()).findByText(/No queda partida para proponer su texto de citas/)).toBeVisible();
  });

  it("si la propuesta no se pudo escribir, lo dice y deja reintentarlo", async () => {
    const user = userEvent.setup();
    const { actions } = row({ ...ON, state: "prepared", published: { on: false }, job: { id: "j1", status: "failed" } });
    expect(within(agendaRow()).getByText("No se pudo proponer cómo cambia su texto de citas. Las herramientas sí cambiaron.")).toBeVisible();
    await user.click(within(agendaRow()).getByRole("button", { name: "Reintentar" }));
    expect(actions.set).toHaveBeenCalledWith({ ref: REF, agent: AGENT, enabled: true });
  });
});

describe("la fila de la agenda · qué puede hacer (2.4)", () => {
  it("con la agenda activa, el menú abre sus herramientas y se apaga una sola", async () => {
    const user = userEvent.setup();
    const { actions } = row(ON);
    await user.click(within(agendaRow()).getByRole("button", { name: "Más acciones de la agenda" }));
    await user.click(await screen.findByRole("menuitem", { name: "Qué puede hacer" }));
    const dialog = await screen.findByRole("dialog", { name: "Herramientas de Agenda (Reservas)" });
    expect(actions.tools).toHaveBeenCalledWith({ ref: REF, agent: AGENT, lang: "es" });
    await user.click(await within(dialog).findByRole("switch", { name: /Apuntar en la lista de espera/ }));
    await waitFor(() => expect(actions.setTool).toHaveBeenCalledWith({ ref: REF, agent: AGENT, key: "reservas.join_waitlist", enabled: false }));
  });

  it("quien solo lee no activa ni desactiva, y ve lo que puede hacer", async () => {
    row(ON, {}, { canWrite: false });
    expect(within(agendaRow()).queryByRole("button", { name: /Desactivar/ })).toBeNull();
    expect(within(agendaRow()).getByRole("button", { name: "Qué puede hacer" })).toBeVisible();
  });

  it("sin la agenda activa no hay «Qué puede hacer»: se activa entera, no de una en una", () => {
    row(AGENDA);
    expect(within(agendaRow()).queryByRole("button", { name: "Más acciones de la agenda" })).toBeNull();
    expect(within(agendaRow()).queryByRole("button", { name: "Qué puede hacer" })).toBeNull();
  });
});

/**
 * Revisión de las puertas de UI (spec 057, 3.1 y 3.5): con la agenda activa en
 * un agente estructurado, sin trabajo en curso ni propuesta abierta (Spa Jemma:
 * la agenda llegó publicada y el texto seguía mandando la cita al equipo), la
 * fila ofrece «Pedir la propuesta», que repite el mismo `PUT` para que la API la
 * encole. La línea de la propuesta vive en un `role="status"` siempre montado:
 * cambia su contenido, no aparece y desaparece. Los nombres accesibles contienen
 * el texto visible, también en inglés (WCAG 2.5.3).
 */
describe("la fila de la agenda · pedir la propuesta (revisión de UI)", () => {
  it("activa, estructurada, sin trabajo ni propuesta: «Pedir la propuesta» repite el PUT sin decir que se activó", async () => {
    const user = userEvent.setup();
    const set = vi.fn<Actions["set"]>(async () => ok({ ...ON, job: { id: "j2", status: "running" } }));
    row(ON, { set, load: vi.fn(async () => ok({ ...ON, proposal: { id: "p2", status: "open" as const } })) });
    const line = within(agendaRow()).getByRole("status");
    expect(line).toHaveAttribute("data-slot", "agenda-text");
    await user.click(within(line).getByRole("button", { name: "Pedir la propuesta" }));
    expect(set).toHaveBeenCalledWith({ ref: REF, agent: AGENT, enabled: true });
    expect(toast.success).not.toHaveBeenCalled();
    // La misma región, con lo de ahora: primero se escribe, después está abierta.
    expect(await within(line).findByText("Hay una propuesta para su texto de citas.")).toBeVisible();
    expect(within(agendaRow()).getAllByRole("status")).toHaveLength(1);
  });

  it("no se ofrece sin la agenda, en un agente de instrucciones libres, con una abierta o con una en curso", () => {
    for (const agenda of [
      AGENDA,
      { ...ON, structured: false },
      { ...ON, proposal: { id: "p1", status: "open" as const } },
      { ...ON, job: { id: "j1", status: "running" } },
    ]) {
      const { unmount } = row(agenda);
      expect(within(agendaRow()).queryByRole("button", { name: "Pedir la propuesta" })).toBeNull();
      unmount();
    }
  });

  it("quien solo lee no la pide", () => {
    row(ON, {}, { canWrite: false });
    expect(within(agendaRow()).queryByRole("button", { name: "Pedir la propuesta" })).toBeNull();
  });

  it("quitada del borrador y aún publicada, dice que las citas ya dadas siguen en Reservas", () => {
    row({ ...ON, draft: { on: false, tools_on: 0 }, state: "on" });
    expect(within(agendaRow()).getByText(/Deja de reservar al publicar\. Las citas ya dadas siguen en Reservas\./)).toBeVisible();
  });

  it("en inglés, el nombre accesible de cada botón contiene su texto visible", () => {
    for (const agenda of [AGENDA, ON]) {
      const { unmount } = render(
        <LocaleProvider locale="en">
          <ul aria-label="Connectors">
            <AgendaRow refId={REF} agentId={AGENT} canWrite agenda={agenda} actions={{ load: vi.fn(), set: vi.fn(), tools: vi.fn(), setTool: vi.fn() }} />
          </ul>
        </LocaleProvider>,
      );
      for (const button of within(agendaRow()).getAllByRole("button")) {
        const visible = (button.textContent ?? "").trim();
        if (!visible) continue;
        expect((button.getAttribute("aria-label") ?? visible).toLowerCase()).toContain(visible.toLowerCase());
      }
      unmount();
    }
  });
});
