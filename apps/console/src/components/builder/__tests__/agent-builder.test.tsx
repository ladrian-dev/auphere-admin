import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentSpec, BuilderDraft, Proposal } from "@/lib/backend/builder-types";

import { HISTORY, REVIEW, job, noWait, ok as okData, preview, session, suite } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({
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
  skills: [{ key: "agendapro", enabled: true, integration: "agendapro", fallback: "Pasa la conversación al equipo." }],
  tools: [],
  connection_requests: [{ integration: "agendapro", reason: "Para reservar en su agenda" }],
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

beforeEach(() => {
  toast.success.mockClear();
});

describe("la pantalla del agente · leer", () => {
  it("pinta cada bloque del AgentSpec, sus pruebas y las propuestas, y pasa axe", async () => {
    const { container } = screenWith();
    expect(screen.getByRole("heading", { level: 2, name: "Recepción" })).toBeVisible();
    expect(screen.getByText("Borrador v1")).toBeVisible();
    expect(screen.getByText("Sin publicar")).toBeVisible();
    expect(screen.getByText("8 pruebas")).toBeVisible();
    const order = Array.from(container.querySelectorAll("[data-block]")).map((el) => el.getAttribute("data-block"));
    expect(order).toEqual(["identity", "voice", "instructions", "procedures", "services", "skills", "escalation", "rules", "ai_disclosure"]);
    expect(within(block("identity")).getByText("Objetivo: Llenar la agenda")).toBeVisible();
    expect(within(block("voice")).getByText("Tú")).toBeVisible();
    expect(within(block("escalation")).getByText("Cuando pide hablar con una persona")).toBeVisible();
    expect(within(block("escalation")).getByText("Si pide factura")).toBeVisible();
    expect(within(block("services")).getByText("Atiende todos los servicios de la ficha.")).toBeVisible();
    // 17.6: la habilidad sin su conector lleva «Conectar» en su fila.
    const connect = within(block("skills")).getByRole("link", { name: "Conectar AgendaPro" });
    expect(connect).toHaveAttribute("href", `/clients/${REF}/integrations`);
    expect(screen.getByText("Añadir la regla «No des precios por teléfono»")).toBeVisible();
    expect(screen.getByText("Añade en Reglas")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("quien solo lee no ve «Editar», «Aplicar» ni «Rechazar» (§V)", () => {
    screenWith({}, { canWrite: false });
    expect(screen.queryByRole("button", { name: /Editar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Aplicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rechazar" })).toBeNull();
    expect(screen.getByText("Añadir la regla «No des precios por teléfono»")).toBeVisible();
  });

  it("los servicios y las habilidades se leen, pero no se editan aquí", () => {
    screenWith();
    expect(within(block("services")).queryByRole("button")).toBeNull();
    expect(within(block("skills")).queryByRole("button")).toBeNull();
    expect(within(block("rules")).getByRole("button", { name: "Editar «Reglas»" })).toBeVisible();
  });
});

describe("la pantalla del agente · editar en línea (17.7)", () => {
  it("guarda el AgentSpec entero con la revisión leída y cuenta las pruebas sin ejecutar", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(within(block("rules")).getByRole("button", { name: "Editar «Reglas»" }));
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
    expect(screen.queryByRole("form", { name: "Editar «Reglas»" })).toBeNull();
    expect(within(block("rules")).getByText("No des precios por teléfono")).toBeVisible();
    // El foco vuelve a «Editar» del bloque guardado.
    expect(within(block("rules")).getByRole("button", { name: "Editar «Reglas»" })).toHaveFocus();
  });

  it("el aviso de IA lo decide una persona aquí: sin decidir lo dice, y se guarda decidido (16.6)", async () => {
    // Recorrido UI de la 047: la puerta exige decidirlo y la pantalla no tenía
    // dónde. Un agente nuevo no podía publicarse.
    const user = userEvent.setup();
    const { actions } = screenWith();
    expect(within(block("ai_disclosure")).getByText(/Sin decidir/)).toBeVisible();
    await user.click(within(block("ai_disclosure")).getByRole("button", { name: "Editar «Aviso de IA»" }));
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
    expect(await within(block("ai_disclosure")).findByText(/Lo dice en su primer mensaje/)).toBeVisible();
  });

  it("el aviso de IA no se guarda sin elegir cuándo lo dice", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(within(block("ai_disclosure")).getByRole("button", { name: "Editar «Aviso de IA»" }));
    const form = screen.getByRole("form", { name: "Editar «Aviso de IA»" });
    await user.click(within(form).getByRole("button", { name: "Guardar" }));
    expect(within(form).getByText("Elige cuándo lo dice.")).toBeVisible();
    expect(actions.save).not.toHaveBeenCalled();
  });

  it("comprueba los límites antes de mandar nada", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(within(block("identity")).getByRole("button", { name: "Editar «Qué hace»" }));
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
    await user.click(within(block("procedures")).getByRole("button", { name: "Editar «Procedimientos»" }));
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
    expect(await within(block("identity")).findByText("Objetivo: Vender más cortes")).toBeVisible();
  });
});

describe("la pantalla del agente · propuestas (15.2, 15.3)", () => {
  it("aplicar la decide una persona y vuelve a leer el borrador", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(actions.decide).toHaveBeenCalledWith({ ref: REF, agent: AGENT, proposal: PROPOSAL, decision: "apply" });
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    expect(await screen.findByText("Ninguna propuesta abierta.")).toBeVisible();
  });

  it("una propuesta caducada lo dice y ya no se puede decidir", async () => {
    const user = userEvent.setup();
    screenWith({ decide: vi.fn(async () => ({ ok: false as const, status: 409, message: "", code: "proposal_stale" })) });
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
    await user.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(await screen.findByText("La regla pasa de 300 caracteres")).toBeVisible();
  });
});

describe("la pantalla del agente · probar y guardar (historias 8 y 9)", () => {
  function withQuality(over: Partial<React.ComponentProps<typeof AgentBuilder>> = {}) {
    const actions: Actions = {
      save: vi.fn(),
      reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 7, exists: false, active_number: 2 }), proposals: [] } })),
      decide: vi.fn(),
    };
    const quality = {
      playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
      tests: { load: vi.fn(async () => okData(suite())), run: vi.fn(), poll: vi.fn(), notApplicable: vi.fn(), add: vi.fn() },
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
          quality={{ tests: suite(), preview: preview(), history: HISTORY, sessions: [session()] }}
          actions={actions}
          qualityActions={quality}
          {...over}
        />
      </LocaleProvider>,
    );
    return { ...view, actions, quality };
  }

  it("tiene la barra de «Guardar», el probador, las pruebas, la revisión y el historial, y pasa axe", async () => {
    const { container } = withQuality();
    expect(screen.getByRole("region", { name: "Guardar el agente" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Probador" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "Pruebas" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "Revisión" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "Historial" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Partes del agente" });
    expect(within(nav).getByRole("link", { name: "Pruebas" })).toHaveAttribute("href", "#agente-pruebas");
    await screen.findByRole("list", { name: "Hallazgos" });
    expect(await axeViolations(container)).toEqual([]);
  }, 20_000);

  it("«Arreglar» una prueba o un hallazgo abre el bloque del borrador", async () => {
    const user = userEvent.setup();
    withQuality();
    await user.click(screen.getByRole("button", { name: "Arreglar Reserva una cita en las instrucciones" }));
    expect(screen.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    await screen.findByRole("list", { name: "Hallazgos" });
    await user.click(screen.getByRole("button", { name: "Arreglar en el borrador" }));
    expect(screen.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
  });

  it("después de guardar, el borrador y todo lo demás se vuelve a leer", async () => {
    const user = userEvent.setup();
    const { actions, quality } = withQuality();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    await waitFor(() => expect(quality.history.load).toHaveBeenCalled());
    expect(quality.tests.load).toHaveBeenCalled();
    expect(await screen.findByText("Publicado: v2")).toBeVisible();
    expect(await screen.findByText("No hay cambios sin guardar.")).toBeVisible();
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
          quality={{ tests: suite(), preview: preview(), history: HISTORY, sessions: [] }}
          actions={{
            save: vi.fn(),
            reload: vi.fn(async () => ({ ok: true as const, data: { draft: draftWith({ revision: 7, exists: false, active_number: 2 }), proposals: [] } })),
            decide: vi.fn(),
            header,
          }}
          qualityActions={{
            playground: { open: vi.fn(), send: vi.fn(), setTime: vi.fn(), close: vi.fn() },
            tests: { load: vi.fn(async () => okData(suite())), run: vi.fn(), poll: vi.fn(), notApplicable: vi.fn(), add: vi.fn() },
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
      ask: vi.fn(async () => okData({ text: "Porque la ficha no tiene AgendaPro conectado.", citations: [], proposals: [], fix: null })),
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
    const panel = screen.getByRole("region", { name: "Copiloto" });
    expect(await within(panel).findByText("Porque la ficha no tiene AgendaPro conectado.")).toBeVisible();
    expect(within(panel).getByText("Sobre la prueba «Reserva una cita»")).toBeVisible();
  });
});
