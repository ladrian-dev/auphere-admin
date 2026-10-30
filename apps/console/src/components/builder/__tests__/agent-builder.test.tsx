import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentSpec, AnswersResult, BuilderAnswer, BuilderDraft, Proposal } from "@/lib/backend/builder-types";

import { HISTORY as CHANNEL_HISTORY, page as channelPage } from "./channel-fixtures";
import { HISTORY, REVIEW, job, noWait, ok as okData, preview, session, suite, test } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({
  answerDraftJobAction: vi.fn(),
  builderDraftAction: vi.fn(),
  decideProposalAction: vi.fn(),
  saveAgentSpecAction: vi.fn(),
}));

const { AgentBuilder } = await import("../agent-builder");
type Actions = NonNullable<React.ComponentProps<typeof AgentBuilder>["actions"]>;

/**
 * Spec 047 (historia 7, T081; requisito 17.7) — la pantalla del agente: cada
 * bloque del AgentSpec se lee y se edita en línea, se guarda entero con la
 * revisión leída, un `spec_invalid` dice sus problemas, un 412 enseña los dos
 * cambios, las pruebas dicen cuántas quedan sin ejecutar, y las propuestas se
 * aplican o se rechazan. Quien solo lee no ve botones.
 *
 * Como el prototipo aprobado (`agente.md` §4, §5 y §12): los 9 bloques viven en
 * cinco filas, cada una con su lápiz que abre en el sitio los editores de sus
 * bloques; lo que el prototipo no enseña está plegado en «Más ajustes».
 */

const REF = "barberia-cultor";
const AGENT = "11111111-1111-4111-8111-111111111111";
const PROPOSAL = "44444444-4444-4444-8444-444444444444";

const SPEC: AgentSpec = {
  schema_version: "1",
  mode: "structured",
  identity: { name: "Recepción", description: "Atiende las citas de la barbería por WhatsApp.", goal: "Llenar la agenda" },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  instructions: { sections: [{ title: "Qué haces", body: "Reservas citas y respondes dudas." }] },
  procedures: [{ id: "reservar", title: "Reservar una cita", when: "Cuando piden hora", steps: "Busca hueco y confirma." }],
  services: { mode: "all" },
  skills: [{ key: "reservas", enabled: true, integration: "googlecalendar", fallback: "Pasa la conversación al equipo." }],
  tools: [],
  connection_requests: [{ integration: "googlecalendar", reason: "Para reservar en su calendario" }],
  escalation: { triggers: ["asks_for_human", { custom: "Si pide factura" }], failed_attempts: 2, message: "Te paso con el equipo." },
  rules: ["No ofrezcas descuentos"],
  ai_disclosure: { decided: false },
  model_policy: { kind: "profile", profile: "auto" },
  memory: { scope: "shared" },
};

function draftWith(over: Partial<BuilderDraft> = {}): BuilderDraft {
  return {
    agent_id: AGENT,
    agent_name: "Recepción",
    revision: 4,
    exists: true,
    number: 1,
    version: 7,
    status: "staged",
    base_number: null,
    active_number: null,
    active_version: null,
    author: "luis@ladrian.studio",
    created_at: "2026-10-27T10:00:00Z",
    updated_at: "2026-10-27T10:00:00Z",
    change_note: null,
    system_prompt: "…",
    tools: [],
    skills: [],
    settings: {} as BuilderDraft["settings"],
    audience: { mode: "everyone", numbers: [], locked: false } as unknown as BuilderDraft["audience"],
    payment_review: { reviewers: [] } as unknown as BuilderDraft["payment_review"],
    screens: [],
    allowed: ["edit", "discard"],
    spec: SPEC,
    tests: { total: 8, stale: 0, case: 8, sector: 0 },
    ...over,
  };
}

const PROPOSALS: Proposal[] = [
  {
    id: PROPOSAL,
    kind: "agent_spec_patch",
    author: "copilot",
    summary: "Añadir la regla «No des precios por teléfono»",
    diff: { ops: [{ op: "add", path: "/rules/-", value: "No des precios por teléfono" }] },
    status: "open",
    created_at: "2026-10-27T10:00:00Z",
    expires_at: "2026-10-27T10:15:00Z",
  },
];

function screenWith(actions: Partial<Actions> = {}, props: Partial<React.ComponentProps<typeof AgentBuilder>> = {}) {
  const full: Actions = {
    save: vi.fn(async ({ spec }) => ({ ok: true as const, data: draftWith({ revision: 5, spec, tests: { total: 8, stale: 8, case: 8, sector: 0 } }) })),
    reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 6 }), proposals: [] } })),
    decide: vi.fn(async () => ({ ok: true as const, data: { id: PROPOSAL, status: "applied", draft_revision: 6 } })),
    ...actions,
  };
  const view = render(
    <LocaleProvider locale="es">
      <AgentBuilder refId={REF} draft={draftWith()} proposals={PROPOSALS} canWrite actions={full} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full };
}

const block = (key: string) => document.querySelector(`[data-block=${key}]`) as HTMLElement;
const row = (key: string) => document.querySelector(`[data-row=${key}]`) as HTMLElement;
const user0 = () => userEvent.setup();
/** «Más ajustes» está plegado: se abre para llegar a lo de dentro. */
async function openMore(user = user0()) {
  const toggle = screen.getByRole("button", { name: /Más ajustes/ });
  if (toggle.getAttribute("aria-expanded") !== "true") await user.click(toggle);
}

beforeEach(() => {
  toast.success.mockClear();
});

describe("la pantalla del agente · leer", () => {
  it("pinta los 9 bloques en las cinco filas del prototipo, las propuestas en «Más ajustes», y pasa axe", async () => {
    const user = userEvent.setup();
    const { container } = screenWith();
    expect(screen.getByRole("heading", { level: 1, name: "Recepción" })).toBeVisible();
    expect(screen.getByText("Borrador v1")).toBeVisible();
    expect(screen.getByText("Sin publicar")).toBeVisible();
    expect(screen.getByText("8 pruebas")).toBeVisible();
    const table = screen.getByRole("region", { name: "Parámetros del agente" });
    expect(within(table).getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Qué hace",
      "Cómo habla",
      "Qué sabe",
      "Qué puede hacer",
      "Cuándo pasa a una persona",
    ]);
    // Qué hace: la descripción, el objetivo y cuántas instrucciones y reglas.
    expect(within(row("does")).getByText("Atiende las citas de la barbería por WhatsApp.")).toBeVisible();
    expect(within(row("does")).getByText("Objetivo: Llenar la agenda")).toBeVisible();
    expect(within(row("does")).getByText("1 sección de instrucciones · 1 regla")).toBeVisible();
    // Cómo habla: una frase, y el aviso de IA sin decidir a la vista (la puerta lo exige).
    expect(within(row("speaks")).getByText("Cercano, de tú.")).toBeVisible();
    expect(within(row("speaks")).getByText("Aviso de IA sin decidir")).toBeVisible();
    expect(within(row("knows")).getByText("Atiende todos los servicios de la ficha.")).toBeVisible();
    expect(within(row("knows")).getByText(/Hereda la ficha del negocio/)).toBeVisible();
    // 17.6: la habilidad sin su conector lleva «Conectar» en su línea; los procedimientos debajo.
    const connect = within(row("can")).getByRole("link", { name: "Conectar Google Calendar" });
    expect(connect).toHaveAttribute("href", `/clients/${REF}/integrations`);
    expect(within(row("can")).getByText("Mientras tanto: Pasa la conversación al equipo.")).toBeVisible();
    expect(within(row("can")).getByText("Para «Reservar una cita»: Cuando piden hora")).toBeVisible();
    expect(within(row("handoff")).getByText("Cuando pide hablar con una persona")).toBeVisible();
    expect(within(row("handoff")).getByText("Si pide factura")).toBeVisible();
    expect(within(row("handoff")).getByText("Mensaje: Te paso con el equipo.")).toBeVisible();
    // Lo que el prototipo no enseña está plegado, y dice si hay propuestas.
    const more = screen.getByRole("button", { name: /Más ajustes/ });
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(within(more).getByText("1 propuesta abierta")).toBeVisible();
    expect(screen.queryByText("Añadir la regla «No des precios por teléfono»")).not.toBeVisible();
    await openMore(user);
    expect(screen.getByText("Añadir la regla «No des precios por teléfono»")).toBeVisible();
    expect(screen.getByText("Añade en Reglas")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  }, 20_000);

  it("quien solo lee no ve «Editar», «Aplicar» ni «Rechazar» (§V)", async () => {
    screenWith({}, { canWrite: false });
    await openMore();
    expect(screen.queryByRole("button", { name: /Editar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Aplicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rechazar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Decidir el aviso de IA" })).toBeNull();
    expect(screen.getByText("Añadir la regla «No des precios por teléfono»")).toBeVisible();
  });

  it("los servicios y las habilidades se leen; el lápiz de «Qué puede hacer» abre los procedimientos", async () => {
    const user = userEvent.setup();
    screenWith();
    // Sin conocimiento que enseñar, «Qué sabe» no tiene lápiz: los servicios se editan en la ficha.
    expect(within(row("knows")).queryByRole("button")).toBeNull();
    await user.click(within(row("can")).getByRole("button", { name: "Editar «Qué puede hacer»" }));
    expect(screen.getByRole("form", { name: "Editar «Procedimientos»" })).toBeVisible();
    expect(within(block("skills")).queryByRole("button", { name: /Editar/ })).toBeNull();
    expect(within(block("skills")).getByRole("link", { name: "Conectar Google Calendar" })).toBeVisible();
  });
});

describe("la pantalla del agente · editar en línea (17.7)", () => {
  it("guarda el AgentSpec entero con la revisión leída y cuenta las pruebas sin ejecutar", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    // El lápiz de la fila abre en el sitio el primero de sus editores; el resto, con el suyo.
    await user.click(within(row("does")).getByRole("button", { name: "Editar «Qué hace»" }));
    expect(screen.getByRole("form", { name: "Editar «Qué hace»" })).toBeVisible();
    expect(within(row("does")).getByRole("heading", { level: 3, name: "Instrucciones" })).toBeVisible();
    await user.click(within(block("rules")).getByRole("button", { name: "Editar «Reglas»" }));
    // Un editor a la vez.
    expect(screen.queryByRole("form", { name: "Editar «Qué hace»" })).toBeNull();
    const form = screen.getByRole("form", { name: "Editar «Reglas»" });
    await user.click(within(form).getByRole("button", { name: "Añadir regla" }));
    await user.type(within(form).getByRole("textbox", { name: "Regla 2" }), "No des precios por teléfono");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));

    expect(actions.save).toHaveBeenCalledWith({
      ref: REF,
      agent: AGENT,
      revision: 4,
      spec: { ...SPEC, rules: ["No ofrezcas descuentos", "No des precios por teléfono"] },
    });
    expect(await screen.findByText("8 sin ejecutar")).toBeVisible();
    expect(toast.success).toHaveBeenCalledWith("Guardado en el borrador. Sus pruebas quedan sin ejecutar.");
    // Como el prototipo, guardar cierra la fila; el foco vuelve a su lápiz.
    expect(screen.queryByRole("form", { name: "Editar «Reglas»" })).toBeNull();
    expect(within(row("does")).getByText("1 sección de instrucciones · 2 reglas")).toBeVisible();
    expect(within(row("does")).getByRole("button", { name: "Editar «Qué hace»" })).toHaveFocus();
    await user.click(within(row("does")).getByText("Ver instrucciones y reglas"));
    expect(within(row("does")).getByText("No des precios por teléfono")).toBeVisible();
  });

  it("el aviso de IA lo decide una persona aquí: sin decidir lo dice, y se guarda decidido (16.6)", async () => {
    // Recorrido UI de la 047: la puerta exige decidirlo y la pantalla no tenía
    // dónde. Un agente nuevo no podía publicarse.
    const user = userEvent.setup();
    const { actions } = screenWith();
    expect(within(row("speaks")).getByText("Aviso de IA sin decidir")).toBeVisible();
    await user.click(within(row("speaks")).getByRole("button", { name: "Decidir el aviso de IA" }));
    const form = screen.getByRole("form", { name: "Editar «Aviso de IA»" });
    await user.click(within(form).getByRole("radio", { name: /En su primer mensaje/ }));
    await user.type(within(form).getByRole("textbox", { name: /Con qué palabras/ }), "Soy el asistente de la barbería.");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));
    expect(actions.save).toHaveBeenCalledWith({
      ref: REF,
      agent: AGENT,
      revision: 4,
      spec: { ...SPEC, ai_disclosure: { decided: true, mode: "first_message", text: "Soy el asistente de la barbería." } },
    });
    expect(await within(row("speaks")).findByText("Aviso de IA: lo dice en su primer mensaje")).toBeVisible();
  });

  it("el aviso de IA no se guarda sin elegir cuándo lo dice", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    // También desde el lápiz de «Cómo habla»: la fila tiene el editor de la voz y el del aviso.
    await user.click(within(row("speaks")).getByRole("button", { name: "Editar «Cómo habla»" }));
    expect(screen.getByRole("form", { name: "Editar «Cómo habla»" })).toBeVisible();
    await user.click(within(block("ai_disclosure")).getByRole("button", { name: "Editar «Aviso de IA»" }));
    const form = screen.getByRole("form", { name: "Editar «Aviso de IA»" });
    await user.click(within(form).getByRole("button", { name: "Guardar" }));
    expect(within(form).getByText("Elige cuándo lo dice.")).toBeVisible();
    expect(actions.save).not.toHaveBeenCalled();
  });

  it("comprueba los límites antes de mandar nada", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(within(row("does")).getByRole("button", { name: "Editar «Qué hace»" }));
    const form = screen.getByRole("form", { name: "Editar «Qué hace»" });
    const description = within(form).getByRole("textbox", { name: /¿Qué tiene que hacer\?/ });
    await user.clear(description);
    await user.type(description, "Corta");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));
    expect(actions.save).not.toHaveBeenCalled();
    expect(within(form).getByText("Entre 20 y 1024 caracteres.", { selector: "[role=alert]" })).toBeVisible();
  });

  it("un `spec_invalid` dice sus problemas y deja el bloque abierto con lo escrito", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => ({
      ok: false as const,
      status: 422,
      message: "",
      code: "spec_invalid",
      info: { problems: [{ pointer: "/procedures/0/steps", code: "unknown_tool", message: "Cita una herramienta que no existe: reservas.borrar" }] },
    }));
    const { container } = screenWith({ save });
    await user.click(within(row("can")).getByRole("button", { name: "Editar «Qué puede hacer»" }));
    const form = screen.getByRole("form", { name: "Editar «Procedimientos»" });
    const steps = within(form).getByRole("textbox", { name: /Pasos del procedimiento 1/ });
    await user.clear(steps);
    await user.type(steps, "Usa reservas.borrar.");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("El borrador no se guardó: el validador encontró esto")).toBeVisible();
    expect(screen.getByText("Cita una herramienta que no existe: reservas.borrar")).toBeVisible();
    expect(within(screen.getByRole("form", { name: "Editar «Procedimientos»" })).getByRole("textbox", { name: /Pasos del procedimiento 1/ })).toHaveValue(
      "Usa reservas.borrar.",
    );
    expect(await axeViolations(container)).toEqual([]);
  });

  it("un 412 enseña los dos cambios, y «Guardar los míos encima» pone mi bloque sobre el borrador de ahora", async () => {
    const user = userEvent.setup();
    const theirs = draftWith({
      revision: 9,
      spec: { ...SPEC, identity: { ...SPEC.identity, goal: "Vender más cortes" } },
    });
    const save = vi
      .fn<Actions["save"]>()
      .mockResolvedValueOnce({
        ok: false,
        status: 412,
        message: "",
        code: "revision_conflict",
        info: { current: theirs, changes: [{ revision: 9, kind: "edit", by: "lucia@ladrian.studio", at: "2026-10-27T10:05:00Z", fields: ["system_prompt"] }] },
      })
      .mockImplementation(async ({ spec, revision }) => ({ ok: true, data: draftWith({ revision: revision + 1, spec }) }));
    screenWith({ save });
    await user.click(within(row("does")).getByRole("button", { name: "Editar «Qué hace»" }));
    await user.click(within(block("rules")).getByRole("button", { name: "Editar «Reglas»" }));
    const form = screen.getByRole("form", { name: "Editar «Reglas»" });
    await user.clear(within(form).getByRole("textbox", { name: "Regla 1" }));
    await user.type(within(form).getByRole("textbox", { name: "Regla 1" }), "Nunca prometas descuentos");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));

    const heading = await screen.findByRole("heading", { name: "Hay cambios más nuevos de lucia@ladrian.studio" });
    expect(heading).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Guardar los míos encima" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenLastCalledWith({
      ref: REF,
      agent: AGENT,
      revision: 9,
      spec: { ...theirs.spec, rules: ["Nunca prometas descuentos"] },
    });
    expect(await within(row("does")).findByText("Objetivo: Vender más cortes")).toBeVisible();
  });
});

describe("la pantalla del agente · propuestas (15.2, 15.3)", () => {
  it("aplicar la decide una persona y vuelve a leer el borrador", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await openMore(user);
    await user.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(actions.decide).toHaveBeenCalledWith({ ref: REF, agent: AGENT, proposal: PROPOSAL, decision: "apply" });
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    expect(await screen.findByText("Ninguna propuesta abierta.")).toBeVisible();
  });

  it("una propuesta caducada lo dice y ya no se puede decidir", async () => {
    const user = userEvent.setup();
    screenWith({ decide: vi.fn(async () => ({ ok: false as const, status: 409, message: "", code: "proposal_stale" })) });
    await openMore(user);
    await user.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(await screen.findByText("Ya no aplica: el borrador cambió después de proponerla. Pide otra.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Aplicar" })).toBeNull();
  });

  it("una propuesta que no pasa el validador enseña sus problemas", async () => {
    const user = userEvent.setup();
    screenWith({
      decide: vi.fn(async () => ({
        ok: false as const,
        status: 422,
        message: "",
        code: "invalid_proposal",
        info: { problems: [{ pointer: "/rules/1", code: "too_long", message: "La regla pasa de 300 caracteres" }] },
      })),
    });
    await openMore(user);
    await user.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(await screen.findByText("La regla pasa de 300 caracteres")).toBeVisible();
  });
});

/** Todas las pruebas pasan: la barra ofrece guardar. */
const PASSING = () =>
  suite({
    summary: { passed: 5, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 1, total: 6, stale: 0, critical_failed: [], rate: 100 },
    tests: [],
  });

describe("la pantalla del agente · probar y guardar (historias 8 y 9)", () => {
  function withQuality(over: Partial<React.ComponentProps<typeof AgentBuilder>> = {}, tests = suite()) {
    const actions: Actions = {
      save: vi.fn(),
      reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 7, exists: false, active_number: 2 }), proposals: [] } })),
      decide: vi.fn(),
    };
    const quality = {
      playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
      tests: {
        load: vi.fn(async () => okData(tests)),
        run: vi.fn(async () => okData({ job_id: "66666666-6666-4666-8666-666666666666", run_id: "r1", tests: 5 })),
        poll: vi.fn(async () => okData(job({ kind: "tests", status: "done" }))),
        notApplicable: vi.fn(),
        add: vi.fn(),
      },
      review: { load: vi.fn(async () => okData(REVIEW)), decide: vi.fn() },
      publish: {
        preview: vi.fn(async () => okData(preview({ has_draft: false }))),
        publish: vi.fn(async () => okData({ job_id: "66666666-6666-4666-8666-666666666666" })),
        poll: vi.fn(async () => okData(job({ status: "done", result: { number: 2, undo_until: new Date(Date.now() + 60_000).toISOString(), gate: {} } }))),
        undo: vi.fn(),
      },
      history: { load: vi.fn(async () => okData(HISTORY)), restore: vi.fn() },
      wait: noWait,
    };
    const view = render(
      <LocaleProvider locale="es">
        <AgentBuilder
          refId={REF}
          draft={draftWith()}
          proposals={[]}
          canWrite
          quality={{ tests, preview: preview(), history: HISTORY, sessions: [session()] }}
          actions={actions}
          qualityActions={quality}
          {...over}
        />
      </LocaleProvider>,
    );
    return { ...view, actions, quality };
  }

  it("a la derecha el chat y las pruebas, abajo la barra de vidrio, y el resto en «Más ajustes»; pasa axe", async () => {
    const user = userEvent.setup();
    const { container, quality } = withQuality();
    const aside = screen.getByRole("complementary", { name: "Pruebas y chat de prueba" });
    // Como el prototipo: pegada al bajar, desde 1060 px.
    expect(aside.className).toMatch(/min-\[1060px\]:sticky/);
    // El owner (2026-10-28): el chat arriba y, justo debajo, «Ejecutar todas» con las pruebas.
    expect(within(aside).getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Chat de prueba · así lo verá su cliente",
      "Pruebas · 2 sin ejecutar",
    ]);
    const runAll = within(aside).getByRole("button", { name: "Ejecutar todas" });
    const composer = within(aside).getByRole("textbox", { name: "Mensaje del cliente" });
    expect(composer.compareDocumentPosition(runAll) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Pegada, nunca más alta que lo que deja la barra flotante: la barra no tapa el chat.
    expect(aside.className).toMatch(/min-\[1060px\]:max-h-\[calc\(100dvh-[0-9]+rem\)\]/);
    expect(aside.className).toMatch(/min-\[1060px\]:overflow-y-auto/);
    const bar = screen.getByRole("region", { name: "Acciones del agente" });
    expect(bar).toBeVisible();
    expect(bar.closest("[data-slot=agent-actionbar]")?.className).toMatch(/(^|\s)glass(\s|$).*sticky|sticky.*(^|\s)glass(\s|$)/);
    expect(within(bar).getByRole("status")).toHaveTextContent("Borrador completo");
    expect(within(bar).getByRole("button", { name: "Ejecutar pruebas" })).toBeVisible();
    // La revisión se lee una vez y la comparten la tarjeta y «Más ajustes».
    await within(aside).findByRole("list", { name: "Revisión automática" });
    expect(screen.queryByRole("heading", { level: 2, name: "Historial" })).toBeNull();
    await openMore(user);
    expect(screen.getByRole("heading", { level: 2, name: "Recepción" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Pruebas" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Revisión" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Historial" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Propuestas" })).toBeVisible();
    await screen.findByRole("list", { name: "Hallazgos" });
    expect(quality.review.load).toHaveBeenCalledTimes(1);
    expect(await axeViolations(container)).toEqual([]);
  }, 30_000);

  it("la tarjeta de pruebas: la que falla con su arreglo, la revisión con los suyos y «Ver las N pruebas»", async () => {
    const user = userEvent.setup();
    withQuality();
    const aside = screen.getByRole("complementary", { name: "Pruebas y chat de prueba" });
    const fail = within(aside).getByRole("alert");
    expect(within(fail).getByText("Falla «Reserva una cita»")).toBeVisible();
    expect(within(fail).getByText("La cita no existe en la agenda al terminar.")).toBeVisible();
    expect(within(fail).getByText("Y 1 más sin pasar.")).toBeVisible();
    const checks = await within(aside).findByRole("list", { name: "Revisión automática" });
    expect(within(checks).getByText(/La habilidad Reservas necesita Google Calendar/)).toBeVisible();
    expect(within(checks).getByText(/El servicio Tinte no tiene precio/)).toBeVisible();
    expect(within(checks).getByRole("link", { name: "Ir a Servicios" })).toHaveAttribute("href", `/clients/${REF}/business#business-services`);
    await user.click(within(aside).getByRole("button", { name: "Ver las 6 pruebas" }));
    expect(screen.getByRole("button", { name: /Más ajustes/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { level: 2, name: "Pruebas" })).toBeVisible();
  });

  it("«Arreglar» una prueba o un hallazgo abre el bloque del borrador en su fila", async () => {
    const user = userEvent.setup();
    withQuality();
    await user.click(screen.getByRole("button", { name: "Arreglar Reserva una cita en las instrucciones" }));
    expect(screen.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
    expect(row("does")).toHaveAttribute("data-open", "true");
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    const checks = await screen.findByRole("list", { name: "Revisión automática" });
    await user.click(within(checks).getByRole("button", { name: "Arreglar en el borrador" }));
    expect(screen.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
  });

  it("con preguntas del borrador sin responder, la barra dice que se puede probar igualmente (§4.5)", () => {
    withQuality({
      questions: {
        job: "22222222-2222-4222-8222-222222222222",
        questions: [
          { id: "q1", text: "¿Hasta qué hora atiende?", why: "No está en la ficha.", options: ["20:00"], target: "/policies/hours", scope: "business", can_be_agent_only: false },
        ],
        discarded: { count: 0, reasons: [] },
      },
    });
    const bar = screen.getByRole("region", { name: "Acciones del agente" });
    expect(within(bar).getByRole("status")).toHaveTextContent("1 pregunta pendiente · puedes probar igualmente");
    expect(within(bar).getByRole("button", { name: "Ejecutar pruebas" })).toBeVisible();
  });

  it("«Ejecutar pruebas» de la barra lanza la pasada y la tarjeta la cuenta", async () => {
    const user = userEvent.setup();
    const { quality } = withQuality();
    await user.click(screen.getByRole("button", { name: "Ejecutar pruebas" }));
    expect(quality.tests.run).toHaveBeenCalledWith({ ref: REF, agent: AGENT, scope: "all" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Pruebas terminadas."));
  }, 15_000);

  it("después de guardar, el borrador y todo lo demás se vuelve a leer", async () => {
    const user = userEvent.setup();
    const { actions, quality } = withQuality({}, PASSING());
    expect(screen.getByRole("heading", { level: 2, name: "Pruebas · 5 de 5 pasan" })).toBeVisible();
    expect(screen.getByText("Todas pasan.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    await waitFor(() => expect(quality.history.load).toHaveBeenCalled());
    expect(quality.tests.load).toHaveBeenCalled();
    expect(await screen.findByText("Publicado: v2")).toBeVisible();
    expect(await screen.findByText("5 de 5 pruebas pasan · guardado")).toBeVisible();
  });
});

describe("la pantalla del agente · la cabecera después de guardar", () => {
  it("vuelve a leer la cabecera: de «Borrador» a lo que es ahora (recorrido UI)", async () => {
    // Al guardar la primera versión la cabecera seguía en «Borrador» hasta
    // recargar la página.
    const user = userEvent.setup();
    const base = {
      id: AGENT,
      name: "Recepción",
      lifecycle: "draft",
      pause_reason: null,
      is_default: true,
      open_conversations: 0,
      paused_by_kind: null,
      paused_origin: null,
      allowed: ["rename", "archive"] as ("rename" | "archive")[],
    };
    const header = vi.fn(async () =>
      okData({ ...base, lifecycle: "published", visible_state: { code: "ready_no_channel", tone: "info", reason: null } }),
    );
    render(
      <LocaleProvider locale="es">
        <AgentBuilder
          refId={REF}
          draft={draftWith()}
          proposals={[]}
          canWrite
          header={{ ...base, visible_state: { code: "draft", tone: "muted", reason: null } } as never}
          agents={[]}
          quality={{ tests: PASSING(), preview: preview(), history: HISTORY, sessions: [] }}
          actions={{
            save: vi.fn(),
            reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 7, exists: false, active_number: 2 }), proposals: [] } })),
            decide: vi.fn(),
            header,
          }}
          qualityActions={{
            playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
            tests: { load: vi.fn(async () => okData(PASSING())), run: vi.fn(), poll: vi.fn(), notApplicable: vi.fn(), add: vi.fn() },
            review: { load: vi.fn(async () => okData(REVIEW)), decide: vi.fn() },
            publish: {
              preview: vi.fn(async () => okData(preview({ has_draft: true }))),
              publish: vi.fn(async () => okData({ job_id: "66666666-6666-4666-8666-666666666666" })),
              poll: vi.fn(async () => okData(job({ status: "done", result: { number: 1, undo_until: null, gate: {} } }))),
              undo: vi.fn(),
            },
            history: { load: vi.fn(async () => okData(HISTORY)), restore: vi.fn() },
            wait: noWait,
          }}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Borrador", { selector: "[data-slot=agent-state] *, [data-slot=agent-state]" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(header).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    expect(await screen.findByText("Listo · sin canal")).toBeVisible();
  });
});

describe("la pantalla del agente · su vida y el copiloto (historias 18 a 20)", () => {
  const HEADER = {
    id: AGENT,
    name: "Recepción",
    lifecycle: "paused",
    pause_reason: "manual",
    visible_state: { code: "paused", tone: "warn", reason: "manual" },
    is_default: true,
    open_conversations: 0,
    paused_by_kind: "partner_member",
    paused_origin: "console",
    allowed: ["rename", "resume", "archive"] as ("rename" | "resume" | "archive")[],
  };

  function withLife() {
    const copilot = {
      ask: vi.fn(async () => okData({ text: "Porque la ficha no tiene Google Calendar conectado.", citations: [], proposals: [], fix: null })),
      fix: vi.fn(),
      decide: vi.fn(),
    };
    const life = {
      rename: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(async () => okData({ ...HEADER, lifecycle: "published", pause_reason: null, visible_state: { code: "serving", tone: "positive", reason: null }, allowed: ["rename", "pause", "archive"] as ("rename" | "pause" | "archive")[] })),
      archive: vi.fn(),
      restore: vi.fn(),
      makeDefault: vi.fn(),
    };
    render(
      <LocaleProvider locale="es">
        <AgentBuilder
          refId={REF}
          draft={draftWith()}
          proposals={[]}
          canWrite
          header={HEADER}
          agents={[]}
          quality={{ tests: suite(), preview: preview(), history: HISTORY, sessions: [] }}
          actions={{ save: vi.fn(), reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith(), proposals: [] } })), decide: vi.fn() }}
          qualityActions={{
            playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
            tests: { load: vi.fn(async () => okData(suite())), run: vi.fn(), poll: vi.fn(), notApplicable: vi.fn(), add: vi.fn() },
            review: { load: vi.fn(async () => okData(REVIEW)), decide: vi.fn() },
            publish: { preview: vi.fn(async () => okData(preview())), publish: vi.fn(), poll: vi.fn(), undo: vi.fn() },
            history: { load: vi.fn(async () => okData(HISTORY)), restore: vi.fn() },
            life,
            copilot,
            wait: noWait,
          }}
        />
      </LocaleProvider>,
    );
    return { copilot, life };
  }

  it("la cabecera dice su estado, si es por defecto y que está en pausa, con su ⋯", async () => {
    const user = userEvent.setup();
    const { life } = withLife();
    expect(screen.getByText("Pausado · a mano")).toBeVisible();
    expect(screen.getByText("Por defecto")).toBeVisible();
    expect(screen.getByText(/En pausa: no responde en ninguno de sus números/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Más acciones de Recepción" }));
    await user.click(await screen.findByRole("menuitem", { name: "Reanudar" }));
    expect(life.resume).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
    expect(await screen.findByText("Atendiendo")).toBeVisible();
    expect(screen.queryByText(/En pausa: no responde/)).toBeNull();
  });

  it("«¿Por qué dijo esto?» en una prueba que falla lo pregunta al copiloto con la prueba", async () => {
    const user = userEvent.setup();
    const { copilot } = withLife();
    await user.click(screen.getByRole("button", { name: "¿Por qué dijo esto en Reserva una cita?" }));
    expect(copilot.ask).toHaveBeenCalledWith({
      ref: REF,
      agent: AGENT,
      message: "¿Por qué dijo esto?",
      context: { test_id: "77777777-7777-4777-8777-000000000002" },
    });
    // El copiloto vive en «Más ajustes»: preguntar lo abre.
    expect(screen.getByRole("button", { name: /Más ajustes/ })).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByRole("region", { name: "Copiloto" });
    expect(await within(panel).findByText("Porque la ficha no tiene Google Calendar conectado.")).toBeVisible();
    expect(within(panel).getByText("Sobre la prueba «Reserva una cita»")).toBeVisible();
  });
});

/**
 * El prototipo aprobado («Consola de partners v2»): el nombre del agente es el
 * título de la página, con su estado y de qué cliente es; debajo, cuatro
 * pestañas en vidrio (Rendimiento · Configuración · Canales · Conectores; el
 * owner, 2026-10-28: «Configurar y probar» se llama solo «Configuración»); un
 * agente que ya atiende abre en Rendimiento, uno sin publicar en Configuración.
 * «Guardar» flota abajo, en vidrio.
 */
describe("la pantalla del agente · como el prototipo", () => {
  const sections = {
    channels: { data: { channels: [], pending_link: null }, pages: {}, canWrite: true, fromPhone: null },
    connectors: { data: [], canWrite: true },
    performance: { performance: null },
    improvements: { data: null },
    qualityActions: { connectors: { load: vi.fn() } },
  } as unknown as Partial<React.ComponentProps<typeof AgentBuilder>>;

  it("el nombre es el título, dice de qué cliente es y lleva cuatro pestañas en vidrio", () => {
    screenWith({}, { ...sections, clientName: "Barbería Cultor", draft: draftWith({ active_number: 2, active_version: 9 }) });
    expect(screen.getByRole("heading", { level: 1, name: "Recepción" })).toBeVisible();
    expect(screen.getByText("de Barbería Cultor")).toBeVisible();
    const tabs = screen.getByRole("tablist", { name: "Secciones del agente" });
    expect(tabs.className).toMatch(/(^|\s)glass(\s|$)/);
    expect(within(tabs).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Rendimiento", "Configuración", "Canales", "Conectores"]);
    expect(screen.queryByRole("navigation", { name: "Partes del agente" })).toBeNull();
  });

  it("sin publicar abre en «Configuración»; publicado, en «Rendimiento»", async () => {
    const user = userEvent.setup();
    const first = screenWith({}, sections);
    expect(screen.getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
    expect(row("does")).toBeVisible();
    first.unmount();
    screenWith({}, { ...sections, draft: draftWith({ active_number: 2, active_version: 9 }) });
    expect(screen.getByRole("tab", { name: "Rendimiento" })).toHaveAttribute("aria-selected", "true");
    expect(row("does")).not.toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Configuración" }));
    expect(row("does")).toBeVisible();
  });

  it("Rendimiento solo existe con una versión guardada (63.2)", () => {
    const first = screenWith({}, sections);
    expect(within(screen.getByRole("tablist")).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Configuración", "Canales", "Conectores"]);
    first.unmount();
    // Un aviso viejo a Rendimiento, sin versión guardada: la pantalla abre en Configuración.
    screenWith({}, { ...sections, initialSection: "agente-rendimiento" });
    expect(screen.getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
  });

  it("un agente «Listo · sin canal» abre en Canales, no en Rendimiento (63.2)", () => {
    const header = {
      id: AGENT,
      name: "Recepción",
      lifecycle: "published",
      pause_reason: null,
      visible_state: { code: "ready_no_channel", tone: "info", reason: null },
      is_default: true,
      open_conversations: 0,
      paused_by_kind: null,
      paused_origin: null,
      allowed: [],
    };
    screenWith({}, { ...sections, header, draft: draftWith({ active_number: 1, active_version: 3 }) });
    expect(screen.getByRole("tab", { name: "Canales" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Rendimiento" })).toBeInTheDocument();
  });

  it("Rendimiento en dos columnas: los 30 días y las sugerencias de esta semana, y la gráfica debajo (H9)", () => {
    const perf = {
      days: 30,
      since: "2026-09-29T00:00:00Z",
      until: "2026-10-29T00:00:00Z",
      conversations: 12,
      resolved_without_person: 9,
      handed_to_person: 3,
      resolved_pct: 75,
      spent: { amount_micros: 1_000_000, currency: "USD" as const },
      spend_per_conversation: null,
      series: [],
    };
    const { container } = screenWith(
      {},
      {
        ...sections,
        draft: draftWith({ active_number: 2, active_version: 9 }),
        performance: { performance: perf },
        improvements: { data: { items: [], allowed: [] } },
        advanced: { cap: { amount_micros: 1_500_000, currency: "EUR" }, spent: null, currency: "EUR", canWrite: true },
      },
    );
    const top = container.querySelector("[data-slot=performance-top]") as HTMLElement;
    expect(within(top).getByRole("region", { name: "Últimos 30 días" })).toBeVisible();
    expect(within(top).getByRole("region", { name: "Sugerencias de esta semana" })).toBeVisible();
    expect(within(top).getByText(/tope 15,00/)).toBeVisible();
    expect(container.querySelector("[data-slot=performance-chart]")).not.toBeNull();
  });

  it("los bloques son las cinco filas de una tabla compacta, con un lápiz por fila", () => {
    screenWith({}, sections);
    const table = screen.getByRole("region", { name: "Parámetros del agente" });
    expect(table.className).toMatch(/divide-y/);
    expect(table.className).toMatch(/rounded-lg/);
    const edit = within(row("speaks")).getByRole("button", { name: "Editar «Cómo habla»" });
    expect(edit.textContent).toBe("");
  });

  it("«Qué sabe» resume la ficha y sus fuentes, y su lápiz abre el conocimiento propio", async () => {
    const user = userEvent.setup();
    screenWith(
      {},
      {
        ...sections,
        business: { services: 5, locations: 1, hours: true },
        knowledge: { data: { items: [], business_sources: 0 }, canWrite: true },
      },
    );
    expect(within(row("knows")).getByText("5 servicios · 1 sede · horario (de la ficha)")).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "Lo que solo sabe este agente", hidden: true })).not.toBeVisible();
    await user.click(within(row("knows")).getByRole("button", { name: "Editar «Qué sabe»" }));
    expect(screen.getByRole("heading", { level: 3, name: "Lo que solo sabe este agente" })).toBeVisible();
    expect(within(row("knows")).getByRole("button", { name: "Enseñar" })).toBeVisible();
    await user.click(within(row("knows")).getByRole("button", { name: "Cerrar «Qué sabe»" }));
    expect(within(row("knows")).getByRole("button", { name: "Editar «Qué sabe»" })).toHaveFocus();
  });

  it("una habilidad con su conector lo dice; la que no lo tiene lleva a la pestaña Conectores", async () => {
    const user = userEvent.setup();
    const spec: AgentSpec = {
      ...SPEC,
      skills: [...(SPEC.skills ?? []), { key: "pedidos", enabled: true, integration: "woocommerce" }],
    };
    screenWith({}, { ...sections, draft: draftWith({ spec }) });
    expect(within(row("can")).getByText("WooCommerce · conectado")).toBeVisible();
    await user.click(within(row("can")).getByRole("button", { name: "Conectar Google Calendar" }));
    expect(screen.getByRole("tab", { name: "Conectores" })).toHaveAttribute("aria-selected", "true");
  });

  it("«Conectar {X}» de una habilidad abre aquí mismo el diálogo de conectar; al conectar, la línea dice «conectado» y se vuelve a leer el borrador (62.3; H11)", async () => {
    const user = userEvent.setup();
    const gcal = { slug: "googlecalendar", name: "Google Calendar", category: "calendar", logo: null, auth_kind: "oauth_composio", needed: true, connection: null, activation: null, settings_schema: null };
    const connected = { ...gcal, connection: { id: "c1", status: "connected", last_checked_at: null }, activation: { permission: "read" as const, settings: {} } };
    const connect = vi.fn(async () => okData({ status: "activated" as const, connection_id: "c1" }));
    const load = vi.fn(async () => okData([connected]));
    const reload = vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 6 }), proposals: [] } }));
    screenWith({ reload }, { ...sections, connectors: { data: [gcal], canWrite: true }, qualityActions: { connectors: { load, connect, open: vi.fn() } } });
    await user.click(within(row("can")).getByRole("button", { name: "Conectar Google Calendar" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar Google Calendar" });
    // Sin salir de la pantalla: la pestaña sigue en «Configuración» (detrás del diálogo).
    expect(screen.getByRole("tab", { name: "Configuración", hidden: true })).toHaveAttribute("aria-selected", "true");
    await user.click(within(dialog).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(connect).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "googlecalendar", permission: "read" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(await within(row("can")).findByText("Google Calendar · conectado")).toBeVisible();
    expect(within(row("can")).queryByRole("button", { name: "Conectar Google Calendar" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
  });

  it("un aviso que lleva a algo de «Más ajustes» lo abre", () => {
    screenWith({}, { ...sections, initialSection: "agente-propuestas" });
    expect(screen.getByRole("button", { name: /Más ajustes/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Añadir la regla «No des precios por teléfono»")).toBeVisible();
  });

  it("un enlace a un bloque abre su fila con su editor", async () => {
    window.location.hash = "#bloque-escalation";
    try {
      screenWith({}, sections);
      expect(await screen.findByRole("form", { name: "Editar «Cuándo pasa a una persona»" })).toBeVisible();
      expect(row("handoff")).toHaveAttribute("data-open", "true");
    } finally {
      window.location.hash = "";
    }
  });

  it("un aviso que lleva a una sección abre su pestaña", () => {
    screenWith({}, { ...sections, initialSection: "agente-conectores" });
    expect(screen.getByRole("tab", { name: "Conectores" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("region", { name: "Conectores" })).toBeVisible();
  });
});

/**
 * Spec 047 (requisito 63.1; H5; T211): la configuración de un canal se pinta
 * dentro del agente, en su pestaña Canales (`?canal=`), con la cabecera y las
 * pestañas del agente arriba. Cambiar de pestaña la cierra.
 */
describe("la pantalla del agente · el canal dentro del agente (63.1)", () => {
  const sections = {
    channels: { data: { channels: [], pending_link: null }, pages: {}, canWrite: true, fromPhone: false },
    connectors: { data: [], canWrite: true },
    qualityActions: { connectors: { load: vi.fn() } },
  } as unknown as Partial<React.ComponentProps<typeof AgentBuilder>>;
  const channelConfig = { page: channelPage({ agent: { id: AGENT, name: "Recepción" } }), history: CHANNEL_HISTORY, canWrite: true, balance: null };

  beforeEach(() => router.replace.mockClear());

  it("abre en Canales con la cabecera del agente arriba y la del canal dentro", () => {
    screenWith({}, { ...sections, channelConfig });
    expect(screen.getByRole("heading", { level: 1, name: "Recepción" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Canales" })).toHaveAttribute("aria-selected", "true");
    const config = document.querySelector("[data-slot=channel-page]") as HTMLElement;
    expect(config).toBeVisible();
    expect(within(config).getByRole("heading", { level: 2, name: "+34 611 20 48 93" })).toBeVisible();
    expect(within(config).getByText("WhatsApp · canal de Recepción")).toBeVisible();
    // La lista de números sigue montada, oculta, mientras la configuración está abierta.
    expect(document.querySelector("[data-slot=agent-channels]")).not.toBeVisible();
  });

  it("cambiar de pestaña cierra la configuración del canal y quita `?canal=` de la dirección", async () => {
    const user = userEvent.setup();
    screenWith({}, { ...sections, channelConfig });
    await user.click(screen.getByRole("tab", { name: "Configuración" }));
    expect(screen.getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
    expect(router.replace).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`, { scroll: false });
    await user.click(screen.getByRole("tab", { name: "Canales" }));
    expect(document.querySelector("[data-slot=channel-page]")).toBeNull();
    expect(document.querySelector("[data-slot=agent-channels]")).toBeVisible();
  });

  it("si el canal pedido no se pudo leer, abre Canales con la lista y lo dice (T218)", async () => {
    const user = userEvent.setup();
    screenWith({}, { ...sections, channelUnavailable: true });
    expect(screen.getByRole("tab", { name: "Canales" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos abrir la configuración de ese número.");
    expect(document.querySelector("[data-slot=agent-channels]")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Configuración" }));
    await user.click(screen.getByRole("tab", { name: "Canales" }));
    expect(screen.queryByText(/No pudimos abrir la configuración de ese número/)).toBeNull();
  });

  it("«Decidir luego» vuelve a la lista de canales", async () => {
    const user = userEvent.setup();
    const unset = channelPage({ agent: { id: AGENT, name: "Recepción" }, config: { ...channelPage().config, audience: { mode: "unset", test_numbers: [], exceptions: [] } } });
    screenWith({}, { ...sections, channelConfig: { ...channelConfig, page: unset } });
    await user.click(screen.getByRole("button", { name: "Decidir luego" }));
    expect(screen.getByRole("tab", { name: "Canales" })).toHaveAttribute("aria-selected", "true");
    expect(document.querySelector("[data-slot=channel-page]")).toBeNull();
    expect(document.querySelector("[data-slot=agent-channels]")).toBeVisible();
    expect(router.replace).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`, { scroll: false });
  });
});

/**
 * Spec 047 (requisito 64; D55; T214): mientras Auphere gestiona los modelos,
 * Avanzado no enseña «Calidad» ni «Fijar un modelo»: lo dice en una línea. Un
 * aviso viejo que lleva a `?tab=quality` cae en esa línea.
 */
describe("la pantalla del agente · Avanzado sin «Calidad» (64.1)", () => {
  const advanced = { cap: null, spent: { amount_micros: 0, currency: "EUR" as const }, currency: "EUR" as const, canWrite: true };

  it("dice que el modelo lo gestiona Auphere, sin «Calidad» ni «Fijar un modelo»", async () => {
    screenWith({}, { advanced });
    await openMore();
    const region = screen.getByRole("region", { name: "Avanzado" });
    expect(within(region).getByText("El modelo de este agente lo gestiona Auphere.")).toBeVisible();
    expect(within(region).queryByRole("heading", { name: "Calidad" })).toBeNull();
    expect(screen.queryByText(/Fijar un modelo/)).toBeNull();
    expect(screen.queryByRole("radiogroup", { name: /calidad/i })).toBeNull();
  });

  it("sin permiso para el tope, Avanzado sigue diciendo quién gestiona el modelo; `?tab=quality` llega a esa línea", () => {
    screenWith({}, { initialSection: "agente-calidad" });
    expect(screen.getByRole("button", { name: /Más ajustes/ })).toHaveAttribute("aria-expanded", "true");
    const line = document.getElementById("agente-calidad") as HTMLElement;
    expect(line).toHaveTextContent("El modelo de este agente lo gestiona Auphere.");
    expect(line).toBeVisible();
  });
});

/**
 * «Nuevo agente» termina en la pantalla del agente (prototipo §3.3, hueco H7):
 * si al borrador le faltan datos, las preguntas salen encima de la tabla y se
 * responden una a una, en el sitio. Elegir una opción la guarda al momento (con
 * su `scope`), la fila se vuelve a leer y la pregunta queda respondida. Nunca
 * se nombra al constructor.
 */
describe("la pantalla del agente · las preguntas que faltan (§3.3)", () => {
  const JOB = "22222222-2222-4222-8222-222222222222";
  const QUESTIONS = {
    job: JOB,
    questions: [
      {
        id: "cancelacion",
        text: "¿Con cuánto tiempo hay que avisar para cancelar una cita?",
        why: "El agente lo dirá al confirmar cada cita.",
        options: ["24 horas antes", "2 horas antes"],
        target: "/policies/cancellation",
        scope: "business" as const,
        can_be_agent_only: true,
      },
      {
        id: "saludo",
        text: "¿Cómo saluda al empezar?",
        why: "Es lo primero que lee el cliente.",
        options: null,
        target: "/identity/goal",
        scope: "agent" as const,
        can_be_agent_only: false,
      },
    ],
    discarded: { count: 2, reasons: ["Ya estaba en la ficha del negocio.", "Repetía otra pregunta."] },
  };
  const applied = (body: { answers: BuilderAnswer[] }) =>
    okData<AnswersResult>({
      applied: body.answers.map((a) => ({ question_id: a.question_id, scope: a.scope ?? "agent", target: "/x" })),
      agent_id: AGENT,
      draft_revision: 5,
      tests_stale: 8,
    });
  const cancel = () => screen.getByRole("group", { name: "¿Con cuánto tiempo hay que avisar para cancelar una cita?" });

  beforeEach(() => window.sessionStorage.clear());

  it("encima de la tabla: cuántos faltan, las descartadas, y cada una con su porqué y dónde se guarda; pasa axe", async () => {
    const { container } = screenWith({ answer: vi.fn() }, { questions: QUESTIONS });
    const section = screen.getByRole("region", { name: "Me faltan 2 datos" });
    const table = screen.getByRole("region", { name: "Parámetros del agente" });
    expect(section.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(section).getByText("No están en la ficha del negocio")).toBeVisible();
    expect(within(section).getByText("Validé 4 preguntas posibles y descarté 2:")).toBeVisible();
    expect(within(section).getByText("Repetía otra pregunta.")).toBeVisible();
    expect(within(cancel()).getByText("El agente lo dirá al confirmar cada cita.")).toBeVisible();
    expect(within(cancel()).getByText("Se guarda en la ficha: lo usarán todos sus agentes.")).toBeVisible();
    expect(within(cancel()).getByRole("button", { name: "24 horas antes" })).toHaveAttribute("aria-pressed", "false");
    expect(within(section).queryByText(/constructor/i)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("elegir una opción la guarda al momento con su `scope`, la deja respondida y vuelve a leer el borrador", async () => {
    const user = userEvent.setup();
    const answer = vi.fn(async (body: { ref: string; job: string; answers: BuilderAnswer[] }) => applied(body));
    const { actions } = screenWith({ answer }, { questions: QUESTIONS });
    await user.click(within(cancel()).getByRole("checkbox", { name: "Solo este agente" }));
    expect(within(cancel()).getByText("Se guarda solo en este agente.")).toBeVisible();
    await user.click(within(cancel()).getByRole("button", { name: "2 horas antes" }));
    expect(answer).toHaveBeenCalledWith({ ref: REF, job: JOB, answers: [{ question_id: "cancelacion", value: "2 horas antes", scope: "agent" }] });
    expect(await screen.findByRole("heading", { level: 2, name: "Me falta 1 dato" })).toBeVisible();
    expect(screen.getByText("2 horas antes · solo en este agente")).toBeVisible();
    expect(screen.queryByRole("group", { name: /cancelar una cita/ })).toBeNull();
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
  });

  it("la que no tiene opciones se responde con su campo y «Guardar»; con todo respondido lo dice y ofrece probarlo", async () => {
    const user = userEvent.setup();
    const answer = vi.fn(async (body: { ref: string; job: string; answers: BuilderAnswer[] }) => applied(body));
    screenWith({ answer }, { questions: QUESTIONS });
    await user.click(within(cancel()).getByRole("button", { name: "24 horas antes" }));
    const open = await screen.findByRole("group", { name: "¿Cómo saluda al empezar?" });
    expect(within(open).getByText("Se guarda solo en este agente.")).toBeVisible();
    await user.type(within(open).getByRole("textbox", { name: "Tu respuesta" }), "¡Hola! Soy Recepción.");
    await user.click(within(open).getByRole("button", { name: "Guardar" }));
    expect(answer).toHaveBeenLastCalledWith({ ref: REF, job: JOB, answers: [{ question_id: "saludo", value: "¡Hola! Soy Recepción.", scope: "agent" }] });
    expect(await screen.findByRole("heading", { level: 2, name: "Todo respondido" })).toBeVisible();
    expect(toast.success).toHaveBeenCalledWith("Todo respondido. Ya puedes probarlo.", expect.objectContaining({ action: expect.objectContaining({ label: "Pruébalo" }) }));
  });

  it("una respuesta que no vale lo dice en su pregunta y la deja abierta", async () => {
    const user = userEvent.setup();
    const answer = vi.fn(async () => ({ ok: false as const, status: 422, message: "", code: "invalid_answer", info: { question_id: "cancelacion" } }));
    screenWith({ answer }, { questions: QUESTIONS });
    await user.click(within(cancel()).getByRole("button", { name: "24 horas antes" }));
    expect(await within(cancel()).findByRole("alert")).toHaveTextContent("Esta respuesta no vale aquí");
    expect(screen.getByRole("heading", { level: 2, name: "Me faltan 2 datos" })).toBeVisible();
  });
});

/**
 * Spec 047, enmienda del 2026-10-30 «Solo lo que tenemos» (T228; requisitos
 * 65.3, 65.4 y 65.9; `contracts/console-api.md` §11): el borrador dice lo que
 * no tenemos con «No tenemos herramienta para: …» —su `missing_capabilities`—,
 * y nada de eso lleva «Conectar {X}». Una promesa del texto lleva a su punto.
 */
describe("la pantalla del agente · solo lo que tenemos (65)", () => {
  const MISSING = [
    { kind: "module" as const, key: "reservas", label: "la agenda (Reservas no está activo para este cliente)", reason: "module_off" as const, source: "connection_request" as const, pointer: null },
    { kind: "action" as const, key: "invoice", label: "emitir facturas", reason: "no_tool" as const, source: "text" as const, pointer: "/procedures/0/steps" },
  ];

  it("encima de la tabla: lo que falta con su `label` y la alternativa del agente; pasa axe", async () => {
    const { container } = screenWith({}, { draft: draftWith({ missing_capabilities: MISSING }) });
    const notice = container.querySelector("[data-slot=missing-capabilities]") as HTMLElement;
    expect(within(notice).getByText("No tenemos herramienta para:")).toBeVisible();
    expect(within(notice).getByText("la agenda (Reservas no está activo para este cliente)")).toBeVisible();
    expect(within(notice).getByText("emitir facturas")).toBeVisible();
    expect(within(notice).getByText("Si se lo piden, el agente pasa la conversación a una persona.")).toBeVisible();
    // Antes de la tabla, para que se lea primero.
    expect(notice.compareDocumentPosition(document.querySelector("[data-slot=agent-rows]")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin nada que falte (o sin el campo), no se enseña nada", () => {
    const { container, unmount } = screenWith({}, { draft: draftWith({ missing_capabilities: [] }) });
    expect(container.querySelector("[data-slot=missing-capabilities]")).toBeNull();
    unmount();
    const second = screenWith();
    expect(second.container.querySelector("[data-slot=missing-capabilities]")).toBeNull();
  });

  it("«Quitar la promesa» abre el bloque donde está; al guardarlo, lo que falta es lo que diga el borrador nuevo", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async ({ spec }: { spec: AgentSpec }) => ({ ok: true as const, data: draftWith({ revision: 5, spec, missing_capabilities: [MISSING[0]!] }) }));
    screenWith({ save }, { draft: draftWith({ missing_capabilities: MISSING }) });
    await user.click(screen.getByRole("button", { name: "Quitar la promesa: emitir facturas" }));
    const form = screen.getByRole("form", { name: "Editar «Procedimientos»" });
    expect(row("can")).toHaveAttribute("data-open", "true");
    const steps = within(form).getByRole("textbox", { name: /Pasos del procedimiento 1/ });
    await user.clear(steps);
    await user.type(steps, "Busca hueco y confirma.");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(screen.queryByText("emitir facturas")).toBeNull());
    expect(screen.getByText("No tenemos herramienta para: la agenda (Reservas no está activo para este cliente)")).toBeVisible();
  });

  it("al volver a leer el borrador, un esqueleto; si no se puede, lo dice y «Reintentar» lo lee otra vez", async () => {
    const user = userEvent.setup();
    let answer: (value: { ok: false; status: number; message: string }) => void = () => undefined;
    const reload = vi
      .fn<Actions["reload"]>()
      .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
      .mockResolvedValueOnce({ ok: true, data: { draft: draftWith({ revision: 7, missing_capabilities: [MISSING[1]!] }), proposals: [] } });
    screenWith({ reload }, { draft: draftWith({ missing_capabilities: MISSING }) });
    await openMore(user);
    await user.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(await screen.findByRole("status", { name: "Comprobando qué herramientas faltan…" })).toBeInTheDocument();
    answer({ ok: false, status: 500, message: "" });
    expect(await screen.findByText("No pudimos comprobar qué herramientas le faltan a este agente.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("No tenemos herramienta para: emitir facturas")).toBeVisible();
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("ningún «Conectar {X}» para lo que no ofrecemos: ni Reservas ni lo que la API dice que falta", () => {
    const spec: AgentSpec = {
      ...SPEC,
      skills: [
        ...(SPEC.skills ?? []),
        { key: "agenda", enabled: true, integration: "reservas", fallback: "Pasa la conversación al equipo." },
        { key: "facturas", enabled: true, integration: "quickbooks" },
      ],
      connection_requests: [
        ...(SPEC.connection_requests ?? []),
        { integration: "reservas", reason: "Para reservar" },
        { integration: "quickbooks", reason: "Para facturar" },
      ],
    };
    const missing = [{ kind: "integration" as const, key: "quickbooks", label: "quickbooks", reason: "integration_unknown" as const, source: "skill" as const, pointer: null }];
    screenWith({}, { draft: draftWith({ spec, missing_capabilities: missing }) });
    const can = row("can");
    expect(within(can).getByRole("link", { name: "Conectar Google Calendar" })).toBeVisible();
    expect(within(can).queryByRole("link", { name: /Conectar Reservas/ })).toBeNull();
    expect(within(can).queryByRole("link", { name: /Conectar Quickbooks/i })).toBeNull();
    // Tampoco se dice «conectado» de lo que no se conecta.
    expect(within(can).queryByText(/Reservas · conectado/)).toBeNull();
    expect(within(can).queryByText(/Quickbooks · conectado/i)).toBeNull();
  });

  it("un `integration_unknown` del validador se dice en palabras, con el conector que pide", async () => {
    const user = userEvent.setup();
    const spec: AgentSpec = { ...SPEC, skills: [{ key: "facturas", enabled: true, integration: "quickbooks" }], connection_requests: [] };
    const save = vi.fn(async () => ({
      ok: false as const,
      status: 422,
      message: "",
      code: "spec_invalid",
      info: { problems: [{ pointer: "/skills/0/integration", code: "integration_unknown", message: "integration 'quickbooks' is not an offered connector" }] },
    }));
    screenWith({ save }, { draft: draftWith({ spec }) });
    await user.click(within(row("does")).getByRole("button", { name: "Editar «Qué hace»" }));
    await user.click(within(screen.getByRole("form", { name: /Editar/ })).getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Quickbooks no es un conector que tengamos para este cliente. Hay que quitar lo que lo pide para poder guardar.")).toBeVisible();
    expect(screen.queryByText(/is not an offered connector/)).toBeNull();
  });
});

describe("la pantalla del agente · pruebas que aplican (65.8, 65.9)", () => {
  // Un agente estructurado cuya única prueba no le aplica (65.8): la puerta no lo publica (65.9).
  const NA = test({
    id: "77777777-7777-4777-8777-000000000009",
    kind: "sector",
    name: "Reserva una cita",
    status: "not_applicable",
    not_applicable_reason: "No aplica: este agente no tiene herramienta para reservar citas.",
    passes: 0,
    decided: 0,
  });
  const tests = suite({
    summary: { passed: 0, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 1, total: 1, stale: 0, critical_failed: [], rate: null },
    tests: [NA],
  });
  const gate = {
    conditions: [{ condition: "critical_tests", ok: false }],
    hard: [{ condition: "critical_tests", code: "no_applicable_tests", message: "Este agente no tiene ninguna prueba que aplique: añade una antes de guardar." }],
    overridable: [],
    normal_failures: [],
    rate: null,
    reference_rate: null,
  };

  function withTests(spec: AgentSpec = SPEC) {
    return render(
      <LocaleProvider locale="es">
        <AgentBuilder
          refId={REF}
          draft={draftWith({ spec })}
          proposals={[]}
          canWrite
          quality={{ tests, preview: preview(), history: HISTORY, sessions: [session()] }}
          actions={{ save: vi.fn(), reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ spec }), proposals: [] } })), decide: vi.fn() }}
          qualityActions={{
            playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
            tests: { load: vi.fn(async () => okData(tests)), run: vi.fn(), poll: vi.fn(), notApplicable: vi.fn(), add: vi.fn() },
            review: { load: vi.fn(async () => okData(REVIEW)), decide: vi.fn() },
            publish: {
              preview: vi.fn(async () => okData(preview())),
              publish: vi.fn(async () => okData({ job_id: "66666666-6666-4666-8666-666666666666" })),
              poll: vi.fn(async () => okData(job({ status: "failed", error_code: "gate_blocked", progress: { step: "blocked", blocks: [{ key: "gate", ...gate }] } }))),
              undo: vi.fn(),
            },
            history: { load: vi.fn(async () => okData(HISTORY)), restore: vi.fn() },
            wait: noWait,
          }}
        />
      </LocaleProvider>,
    );
  }

  it("la puerta sin pruebas aplicables lo dice y «Añadir una prueba» lleva a la lista con su formulario abierto", async () => {
    const user = userEvent.setup();
    withTests();
    const bar = screen.getByRole("region", { name: "Acciones del agente" });
    await user.click(within(bar).getByRole("button", { name: "Guardar" }));
    const sheet = await screen.findByRole("dialog", { name: "Por qué no se guardó" });
    expect(within(sheet).getByText("Este agente no tiene ninguna prueba que le aplique. Añade una antes de guardar.")).toBeVisible();
    await user.click(within(sheet).getByRole("button", { name: "Añadir una prueba" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Por qué no se guardó" })).toBeNull());
    expect(screen.getByRole("button", { name: /Más ajustes/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("form", { name: "Añadir una prueba" })).toBeVisible();
  });

  it("en la lista, un estructurado sin pruebas que le apliquen lo dice; la que no aplica, con su razón y sin repetir «No aplica»", async () => {
    const user = userEvent.setup();
    withTests();
    await openMore(user);
    const list = document.querySelector("[data-slot=test-list]") as HTMLElement;
    expect(within(list).getByText("Ninguna prueba aplica a este agente. Añade una que le aplique: sin ella no se puede guardar.")).toBeVisible();
    expect(within(list).getByText("No aplica: este agente no tiene herramienta para reservar citas.")).toBeVisible();
  });

  it("uno de antes (`instructions`) no lo dice: la puerta no se lo pide", async () => {
    const user = userEvent.setup();
    withTests({ ...SPEC, mode: "instructions" });
    await openMore(user);
    expect(screen.queryByText(/Ninguna prueba aplica a este agente/)).toBeNull();
  });
});
