import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { PlaygroundSession } from "@/lib/backend/agent-quality-types";

import { AGENT, REF, SESSION, fail, ok, session } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({
  closePlaygroundAction: vi.fn(),
  openPlaygroundAction: vi.fn(),
  sendPlaygroundAction: vi.fn(),
  setPlaygroundTimeAction: vi.fn(),
}));

const { AgentPlayground } = await import("../agent-playground");
type Actions = NonNullable<React.ComponentProps<typeof AgentPlayground>["actions"]>;

/**
 * Spec 047 (historia 8, T089; requisito 20) — el probador: las burbujas de
 * WhatsApp y el aviso de varias seguidas, «Lo que habría hecho», la hora
 * simulada en la zona del negocio (que se cambia) y la agenda simulada que
 * cambia con lo que hace el agente. Quien solo lee lo ve sin escribir.
 *
 * Como el prototipo aprobado (§5.2): «Chat de prueba · así lo verá su
 * cliente», la conversación empieza al escribir, y la versión, la hora y la
 * agenda simuladas y «Nueva conversación» van detrás de «Opciones».
 */

const REPLY = {
  turn: {
    role: "agent" as const,
    bubbles: ["¡Claro! Mañana a las 11 tengo hueco.", "Te la dejo reservada para un corte."],
    several_bubbles: true,
    actions: [{ tool: "reservas.create", phrase: "crear cita de Corte el 28/10/2026 a las 11:00" }],
  },
  now: "2026-10-27T11:21:00+01:00",
  agenda: [
    { id: "b1", service: "Corte", when: "28/10/2026 a las 10:00", status: "confirmed" },
    { id: "b2", service: "Corte", when: "28/10/2026 a las 11:00", status: "confirmed" },
  ],
};

function screenWith(props: Partial<React.ComponentProps<typeof AgentPlayground>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    open: vi.fn(async () => ok(session())),
    send: vi.fn(async () => ok(REPLY)),
    setTime: vi.fn(async ({ now }: { now: string }) => ok(session({ now: `${now}+01:00` }))),
    close: vi.fn(async () => ok(null)),
    ...actions,
  };
  const view = render(
    <LocaleProvider locale="es">
      <AgentPlayground refId={REF} agentId={AGENT} sessions={[]} versions={[2, 1]} hasDraft canWrite actions={full} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full };
}

beforeEach(() => toast.success.mockClear());

describe("el probador (20.2, 20.3, 20.4)", () => {
  it("como el prototipo: la conversación empieza al escribir, con el borrador", async () => {
    const user = userEvent.setup();
    const { actions, container } = screenWith();
    expect(screen.getByRole("heading", { level: 2, name: "Chat de prueba · así lo verá su cliente" })).toBeVisible();
    expect(screen.getByText(/Escribe como lo haría un cliente/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Empezar una conversación" })).toBeNull();
    const box = screen.getByRole("textbox", { name: "Mensaje del cliente" });
    expect(box).toHaveAttribute("placeholder", "Escribe como un cliente");
    await user.type(box, "¿cuánto cuesta?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(actions.open).toHaveBeenCalledWith({ ref: REF, agent: AGENT, version: "draft" });
    await waitFor(() => expect(actions.send).toHaveBeenCalledWith({ ref: REF, agent: AGENT, session: SESSION, text: "¿cuánto cuesta?" }));
    const chat = screen.getByRole("list", { name: "Conversación de prueba" });
    expect(await within(chat).findByText("¡Claro! Mañana a las 11 tengo hueco.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("la versión se elige en «Opciones» y vale para la conversación siguiente", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith({ sessions: [session()] });
    await user.click(screen.getByRole("button", { name: "Opciones del chat de prueba" }));
    expect(screen.getByText("Probando el borrador v3")).toBeVisible();
    const select = screen.getByRole("combobox", { name: "Qué versión probar" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Borrador", "v2", "v1"]);
    await user.selectOptions(select, "2");
    await user.click(screen.getByRole("button", { name: "Nueva conversación" }));
    expect(actions.close).toHaveBeenCalledWith({ ref: REF, agent: AGENT, session: SESSION });
    expect(actions.open).toHaveBeenCalledWith({ ref: REF, agent: AGENT, version: 2 });
  });

  it("las respuestas son burbujas, dice si fueron varias y qué habría hecho, y la agenda cambia", async () => {
    const user = userEvent.setup();
    const { actions, container } = screenWith({ sessions: [session()] });
    await user.click(screen.getByRole("button", { name: "Opciones del chat de prueba" }));
    expect(screen.getByText("Corte · 28/10/2026 a las 10:00")).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "Mensaje del cliente" }), "quiero reservar mañana a las 11");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(actions.send).toHaveBeenCalledWith({ ref: REF, agent: AGENT, session: SESSION, text: "quiero reservar mañana a las 11" });

    const chat = screen.getByRole("list", { name: "Conversación de prueba" });
    expect(await within(chat).findByText("¡Claro! Mañana a las 11 tengo hueco.")).toBeVisible();
    expect(within(chat).getByText("quiero reservar mañana a las 11")).toBeVisible();
    expect(within(chat).getByText("Respondió en 2 mensajes seguidos")).toBeVisible();
    expect(within(chat).getByText("Lo que habría hecho: crear cita de Corte el 28/10/2026 a las 11:00")).toBeVisible();
    expect(screen.getByText("Corte · 28/10/2026 a las 11:00")).toBeVisible();
    expect(container.querySelectorAll("[data-slot=playground-bubble]")).toHaveLength(3);
    expect(screen.getByRole("textbox", { name: "Mensaje del cliente" })).toHaveValue("");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("la hora se dice en la zona del negocio y se cambia en su hora de pared", async () => {
    const user = userEvent.setup();
    const { actions, container } = screenWith({ sessions: [session()] });
    // Como el prototipo, la hora simulada se ve en la cabecera del chat.
    expect(screen.getByText(/^mar 11:20$/i, { selector: "[data-slot=playground-clock] *, [data-slot=playground-clock]" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Opciones del chat de prueba" }));
    const now = container.querySelector("[data-slot=playground-now]") as HTMLElement;
    expect(now.textContent).toMatch(/mar.*27.*oct.*11:20/);
    expect(screen.getByText("En la zona del negocio (Europe/Madrid)")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cambiar la hora" }));
    const input = screen.getByLabelText("Nueva hora simulada");
    expect(input).toHaveValue("2026-10-27T11:20");
    await user.clear(input);
    await user.type(input, "2026-11-01T20:30");
    await user.click(screen.getByRole("button", { name: "Usar esta hora" }));
    expect(actions.setTime).toHaveBeenCalledWith({ ref: REF, agent: AGENT, session: SESSION, now: "2026-11-01T20:30:00" });
    await waitFor(() => expect(now.textContent).toMatch(/1.*nov.*20:30/));
  });

  it("dice por qué no respondió: ocupado o tardó demasiado, sin perder lo escrito", async () => {
    const user = userEvent.setup();
    const send = vi.fn<Actions["send"]>().mockResolvedValueOnce(fail(409, "turn_in_progress")).mockResolvedValueOnce(fail(504, "turn_timeout"));
    screenWith({ sessions: [session()] }, { send });
    const box = screen.getByRole("textbox", { name: "Mensaje del cliente" });
    await user.type(box, "hola");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Aún está respondiendo al mensaje anterior. Espera un momento.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Tardó demasiado en responder. Vuelve a intentarlo.")).toBeVisible();
    expect(box).toHaveValue("hola");
  });

  it("quien solo lee ve la conversación sin poder escribir ni cambiar la hora (20.5)", async () => {
    const readonly: PlaygroundSession = session({
      allowed: [],
      transcript: [
        { role: "customer", bubbles: ["¿Abrís el domingo?"], several_bubbles: false, actions: [] },
        { role: "agent", bubbles: ["Los domingos está cerrado."], several_bubbles: false, actions: [] },
      ],
    });
    const { container } = screenWith({ sessions: [readonly], canWrite: false });
    expect(screen.getByText("Los domingos está cerrado.")).toBeVisible();
    expect(screen.getByText(/Solo lectura/)).toBeVisible();
    expect(screen.queryByRole("textbox")).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Opciones del chat de prueba" }));
    expect(screen.getByText("En la zona del negocio (Europe/Madrid)")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Cambiar la hora" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Nueva conversación" })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin conversaciones y sin permiso, lo dice", () => {
    screenWith({ sessions: [], canWrite: false });
    expect(screen.getByText(/Aún no hay conversaciones de prueba/)).toBeVisible();
  });
});
