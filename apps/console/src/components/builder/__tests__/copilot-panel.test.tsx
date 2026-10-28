import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { CopilotAnswer } from "@/lib/backend/agent-life-types";

import { COBROS, REF, fail, ok } from "./life-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({}));

const { CopilotPanel, citationHref } = await import("../copilot-panel");
type Actions = NonNullable<React.ComponentProps<typeof CopilotPanel>["actions"]>;
type Handle = { ask: (message: string, context?: Record<string, unknown>, about?: string) => void };

/**
 * Spec 047 (historia 18, T099; requisito 19) — el copiloto: propuestas
 * revisables a una petición, «¿Por qué dijo esto?» con sus fuentes enlazadas,
 * «Arreglar» un dato que pregunta dónde se corrige y aplica solo entonces, y a
 * quien solo lee le explica sin un control de aplicar.
 */

const TEST = "77777777-7777-4777-8777-000000000002";
const WHY: CopilotAnswer = {
  text: "Dijo que el domingo abrís porque la instrucción «Qué haces» lo dice, y la ficha dice cerrado.",
  citations: [
    { kind: "business", label: "Horario", excerpt: "Domingo: cerrado", link: { target: "business/hours" } },
    { kind: "instruction", label: "Qué haces", excerpt: "Abrimos los domingos.", link: { target: "agent", pointer: "/instructions/sections/0/body" } },
    { kind: "tool", label: "Crear cita", excerpt: "", link: { target: "capabilities", tool: "reservas.create" } },
  ],
  proposals: [
    {
      id: "88888888-8888-4888-8888-888888888888",
      kind: "agent_spec_patch",
      summary: "Quitar «Abrimos los domingos» de las instrucciones",
      diff: { ops: [{ op: "replace", path: "/instructions/sections/0/body", value: "Reservas citas." }] },
      expires_at: "2026-10-27T10:15:00Z",
    },
  ],
  fix: { test_id: TEST, scopes: ["business", "agent"] },
};

function panelWith(props: Partial<React.ComponentProps<typeof CopilotPanel>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    ask: vi.fn(async () => ok(WHY)),
    fix: vi.fn(async () => ok({ scope: "business" as const, faq_id: "f1" })),
    decide: vi.fn(async () => ok({ id: "p", status: "applied", draft_revision: 9 })),
    ...actions,
  };
  const ref = React.createRef<Handle>();
  const onChanged = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <CopilotPanel ref={ref} refId={REF} agentId={COBROS} canWrite onChanged={onChanged} actions={full} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full, ref, onChanged };
}

beforeEach(() => toast.success.mockClear());

describe("el copiloto (19.1, 19.2)", () => {
  it("responde a una petición y cita sus fuentes con enlace", async () => {
    const user = userEvent.setup();
    const { actions, container } = panelWith();
    await user.type(screen.getByRole("textbox", { name: "Mensaje para el copiloto" }), "¿por qué dijo que abrimos el domingo?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(actions.ask).toHaveBeenCalledWith({ ref: REF, agent: COBROS, message: "¿por qué dijo que abrimos el domingo?" });
    const reply = await screen.findByText(/Dijo que el domingo abrís/);
    expect(reply).toBeVisible();
    const sources = container.querySelector("[data-slot=copilot-citations]") as HTMLElement;
    expect(within(sources).getByRole("link", { name: "Abrir Ficha · Horario" })).toHaveAttribute("href", `/clients/${REF}/business#business-hours`);
    expect(within(sources).getByRole("link", { name: "Abrir Instrucción · Qué haces" })).toHaveAttribute("href", "#bloque-instructions");
    expect(within(sources).getByRole("link", { name: "Abrir Herramienta · Crear cita" })).toHaveAttribute("href", `/clients/${REF}/capabilities`);
    expect(within(sources).getByText("«Domingo: cerrado»")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«¿Por qué dijo esto?» llega desde fuera con su contexto", async () => {
    const { actions, ref } = panelWith();
    act(() => ref.current?.ask("¿Por qué dijo esto?", { test_id: TEST }, "Sobre la prueba «Reserva una cita»"));
    expect(actions.ask).toHaveBeenCalledWith({ ref: REF, agent: COBROS, message: "¿Por qué dijo esto?", context: { test_id: TEST } });
    expect(screen.getByText("Sobre la prueba «Reserva una cita»")).toBeVisible();
    expect(await screen.findByText(/Dijo que el domingo abrís/)).toBeVisible();
  });

  it("las propuestas se aplican como cualquier otra (19.3)", async () => {
    const user = userEvent.setup();
    const { actions, onChanged } = panelWith();
    await user.type(screen.getByRole("textbox", { name: "Mensaje para el copiloto" }), "no digas que abrimos el domingo");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Quitar «Abrimos los domingos» de las instrucciones")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(actions.decide).toHaveBeenCalledWith({ ref: REF, agent: COBROS, proposal: "88888888-8888-4888-8888-888888888888", decision: "apply" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("«Arreglar» un dato pregunta dónde se corrige y solo entonces lo aplica (19.4)", async () => {
    const user = userEvent.setup();
    const { actions, onChanged } = panelWith();
    await user.type(screen.getByRole("textbox", { name: "Mensaje para el copiloto" }), "arregla la prueba");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    const form = (await screen.findByRole("group", { name: "¿Dónde lo corrijo?" })).closest("form") as HTMLElement;
    expect(within(form).getByRole("radio", { name: "En la ficha (lo sabrán todos los agentes)" })).toBeVisible();
    await user.click(within(form).getByRole("button", { name: "Corregir" }));
    expect(within(form).getByText("Escribe el dato correcto.")).toBeVisible();
    expect(actions.fix).not.toHaveBeenCalled();
    await user.click(within(form).getByRole("radio", { name: "Solo este agente" }));
    await user.type(within(form).getByRole("textbox", { name: /El dato correcto/ }), "Los domingos está cerrado");
    await user.click(within(form).getByRole("button", { name: "Corregir" }));
    expect(actions.fix).toHaveBeenCalledWith({ ref: REF, agent: COBROS, test: TEST, scope: "agent", value: "Los domingos está cerrado" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("a quien solo lee le explica: ni aplicar ni corregir (19.5)", async () => {
    const user = userEvent.setup();
    panelWith({ canWrite: false });
    expect(screen.getByText(/Las propuestas son para quien puede editar el agente/)).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "Mensaje para el copiloto" }), "¿por qué?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/Dijo que el domingo abrís/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Aplicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Corregir" })).toBeNull();
  });

  it("dice si se acabó la partida de construcción", async () => {
    const user = userEvent.setup();
    panelWith({}, { ask: vi.fn(async () => fail(402, "build_budget_exhausted")) });
    await user.type(screen.getByRole("textbox", { name: "Mensaje para el copiloto" }), "hazlo más breve");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/Se acabó la partida de construcción de este mes/)).toBeVisible();
  });

  it("cada cita lleva a su sitio", () => {
    expect(citationHref(REF, { target: "business/special_dates" })).toBe(`/clients/${REF}/business#business-special-dates`);
    expect(citationHref(REF, { target: "business/policies" })).toBe(`/clients/${REF}/business`);
    expect(citationHref(REF, { target: "agent", pointer: "/services/faqs/0" })).toBe("#bloque-services");
    expect(citationHref(REF, { target: "knowledge" })).toBe(`/clients/${REF}/knowledge`);
    expect(citationHref(REF, null)).toBeNull();
  });
});
