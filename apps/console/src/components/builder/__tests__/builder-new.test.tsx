import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { BuilderBlock, DraftJob, DraftJobResult, DraftOptions } from "@/lib/backend/builder-types";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({
  startDraftJobAction: vi.fn(),
  draftJobAction: vi.fn(),
  answerDraftJobAction: vi.fn(),
}));

const { BuilderNew } = await import("../builder-new");
type Actions = NonNullable<React.ComponentProps<typeof BuilderNew>["actions"]>;

/**
 * Spec 047 (historia 7, T081) — «Nuevo agente»: los límites y los ejemplos a la
 * izquierda, los bloques que llegan en orden a la derecha, las preguntas que
 * dicen dónde se guardan (y mandan su `scope`), las filas «Conectar», las
 * preguntas descartadas con su porqué y, si el constructor no responde, la
 * plantilla y el blanco sin perder lo escrito.
 */

const REF = "barberia-cultor";
const AGENT = "11111111-1111-4111-8111-111111111111";
const JOB = "22222222-2222-4222-8222-222222222222";
const NAME = "Recepción";
const DESCRIPTION = "Atiende las citas de la barbería por WhatsApp y recuerda la política de cancelación.";

const OPTIONS: DraftOptions = {
  examples: ["Atiende las citas de la barbería por WhatsApp: busca hueco, reserva y recuerda la política de cancelación."],
  templates: [
    { id: "barber_v1", name: "Barbería", group: "Belleza", is_default: true },
    { id: "clinic_v1", name: "Clínica", group: "Salud", is_default: false },
    { id: "generic_v1", name: "Genérica", group: "Otro", is_default: false },
  ],
  default_template: "barber_v1",
  name_max: 40,
  description_min: 20,
  description_max: 1024,
};

const ALL_BLOCKS: BuilderBlock[] = [
  { key: "identity", value: { name: NAME, description: DESCRIPTION, goal: "Llenar la agenda" } },
  { key: "voice", value: { tone: "Cercano", languages: ["es"], register: "tu" } },
  { key: "instructions", value: { sections: [{ title: "Qué haces", body: "Reservas citas." }] } },
  { key: "procedures", value: [{ id: "reservar", title: "Reservar una cita", when: "Cuando piden hora", steps: "Busca hueco." }] },
  { key: "services", value: { mode: "all" } },
  {
    key: "skills",
    value: [
      { key: "reservas", enabled: true, integration: null },
      { key: "stripe", enabled: true, integration: "stripe", fallback: "Pasa la conversación al equipo." },
    ],
    connect: [{ integration: "stripe", reason: "Para cobrar con enlace" }],
  },
  { key: "escalation", value: { triggers: ["asks_for_human", "failed_attempts"], failed_attempts: 2 } },
  { key: "rules", value: ["No ofrezcas descuentos"] },
  { key: "tests", count: 8 },
  { key: "questions", count: 2, discarded: 2 },
];

const RESULT: DraftJobResult = {
  agent_id: AGENT,
  questions: [
    {
      id: "cancelacion",
      text: "¿Con cuánto tiempo hay que avisar para cancelar una cita?",
      why: "El agente lo dirá al confirmar cada cita.",
      options: ["24 horas antes", "2 horas antes"],
      target: "/policies/cancellation",
      scope: "business",
      can_be_agent_only: true,
    },
    {
      id: "saludo",
      text: "¿Cómo saluda al empezar?",
      why: "Es lo primero que lee el cliente.",
      options: null,
      target: "/identity/goal",
      scope: "agent",
      can_be_agent_only: false,
    },
  ],
  discarded: { count: 2, reasons: ["Ya estaba en la ficha del negocio.", "Repetía otra pregunta."] },
  connect: [{ integration: "stripe", reason: "Para cobrar con enlace" }],
  dropped_tools: [],
  tests: { case: 8 },
};

function jobWith(over: Partial<DraftJob>): DraftJob {
  return {
    job_id: JOB,
    kind: "agent_draft",
    status: "running",
    agent_id: null,
    progress: { step: "writing", blocks: [] },
    result: null,
    error_code: null,
    created_at: "2026-10-27T10:00:00Z",
    finished_at: null,
    ...over,
  };
}

/** Un `poll` que contesta cuando la prueba lo suelta: así se ve cada paso. */
function gatedPoll(steps: DraftJob[]) {
  const gates: (() => void)[] = [];
  let i = 0;
  const poll = vi.fn(
    () =>
      new Promise<{ ok: true; data: DraftJob }>((resolve) => {
        const step = steps[Math.min(i, steps.length - 1)]!;
        i += 1;
        gates.push(() => resolve({ ok: true, data: step }));
      }),
  );
  async function release() {
    await waitFor(() => expect(gates.length).toBeGreaterThan(0));
    await act(async () => {
      gates.shift()!();
    });
  }
  return { poll, release };
}

function screenWith(actions: Partial<Actions>, options: DraftOptions | null = OPTIONS) {
  const full: Actions = {
    start: vi.fn(async () => ({ ok: true as const, data: { job_id: JOB, status: "queued" as const, agent_id: null } })),
    poll: vi.fn(async () => ({ ok: true as const, data: jobWith({}) })),
    answer: vi.fn(async () => ({ ok: true as const, data: { applied: [], agent_id: AGENT, draft_revision: 3, tests_stale: 8 } })),
    ...actions,
  };
  const view = render(
    <LocaleProvider locale="es">
      <BuilderNew refId={REF} options={options} actions={full} wait={() => new Promise((resolve) => setTimeout(resolve, 0))} />
    </LocaleProvider>,
  );
  return { ...view, actions: full };
}

async function describeAgent(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /Nombre/ }), NAME);
  await user.type(screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ }), DESCRIPTION);
}

const blockOrder = () =>
  Array.from(document.querySelectorAll("[data-slot=builder-blocks] [data-block]")).map((el) => el.getAttribute("data-block"));

beforeEach(() => {
  nav.push.mockClear();
  toast.success.mockClear();
});

describe("«Nuevo agente» · la descripción (17.1)", () => {
  it("dice los límites, cuenta los caracteres y pasa axe", async () => {
    const { container } = screenWith({});
    const name = screen.getByRole("textbox", { name: /Nombre/ });
    const description = screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ });
    expect(name).toHaveAttribute("maxLength", "40");
    expect(description).toHaveAttribute("maxLength", "1024");
    expect(screen.getByText("0 de 40")).toBeInTheDocument();
    expect(screen.getByText("0 de 1024")).toBeInTheDocument();
    expect(screen.getByText(/Entre 20 y 1024 caracteres/)).toBeInTheDocument();
    await userEvent.setup().type(name, "Recepción");
    expect(screen.getByText("9 de 40")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("no empieza nada con una descripción corta o sin nombre, y lo dice junto al campo", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith({});
    await user.type(screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ }), "Muy corta");
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));
    expect(actions.start).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe un nombre de 1 a 40 caracteres.")).toBeVisible();
    expect(screen.getByText(/Cuéntalo en 20 a 1024 caracteres/)).toBeVisible();
    expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveFocus();
  });

  it("un ejemplo se copia en «¿Qué tiene que hacer?»", async () => {
    const user = userEvent.setup();
    screenWith({});
    await user.click(screen.getByRole("button", { name: OPTIONS.examples[0] }));
    const description = screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ });
    expect(description).toHaveValue(OPTIONS.examples[0]);
    expect(description).toHaveFocus();
  });

  it("«Crear este agente» del constructor del cliente llega con su nombre y su descripción (18.4)", () => {
    render(
      <LocaleProvider locale="es">
        <BuilderNew refId={REF} options={OPTIONS} initial={{ name: NAME, description: DESCRIPTION }} actions={{ start: vi.fn(), poll: vi.fn(), answer: vi.fn() }} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue(NAME);
    expect(screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveValue(DESCRIPTION);
  });

  it("un nombre ocupado se dice en el nombre", async () => {
    const user = userEvent.setup();
    screenWith({ start: vi.fn(async () => ({ ok: false as const, status: 409, message: "", code: "name_taken" })) });
    await describeAgent(user);
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));
    expect(await screen.findByText("Ya hay un agente con ese nombre en este cliente. Elige otro.")).toBeVisible();
  });
});

describe("«Nuevo agente» · el borrador por bloques (17.3)", () => {
  it("pinta los bloques en orden según llegan y, sin preguntas, va al agente", async () => {
    const user = userEvent.setup();
    const { poll, release } = gatedPoll([
      jobWith({ progress: { step: "reading", blocks: [] } }),
      jobWith({ progress: { step: "writing", blocks: ALL_BLOCKS.slice(0, 1) } }),
      jobWith({ progress: { step: "writing", blocks: ALL_BLOCKS.slice(0, 4) } }),
      jobWith({
        status: "done",
        agent_id: AGENT,
        progress: { step: "writing", blocks: ALL_BLOCKS },
        result: { ...RESULT, questions: [], discarded: { count: 0, reasons: [] } },
      }),
    ]);
    const { actions } = screenWith({ poll });
    await describeAgent(user);
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));
    expect(actions.start).toHaveBeenCalledWith({ ref: REF, name: NAME, description: DESCRIPTION, start: "describe" });

    await release();
    expect(await screen.findByText("Leyendo la ficha del negocio…")).toBeVisible();
    expect(blockOrder()).toEqual([]);

    await release();
    await waitFor(() => expect(blockOrder()).toEqual(["identity"]));
    expect(screen.getByText("Escribiendo el borrador · 1 de 10 bloques")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Qué hace" })).toBeVisible();

    await release();
    await waitFor(() => expect(blockOrder()).toEqual(["identity", "voice", "instructions", "procedures"]));

    await release();
    await waitFor(() =>
      expect(blockOrder()).toEqual(["identity", "voice", "instructions", "procedures", "services", "skills", "escalation", "rules", "tests", "questions"]),
    );
    expect(poll).toHaveBeenCalledWith({ ref: REF, job: JOB });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`));
    // Sin descartes no hay línea de descartes: ni «0 preguntas».
    expect(document.querySelector("[data-slot=builder-discarded]")).toBeNull();
  });

  it("la habilidad que pide un conector sin conectar lleva «Conectar» en su fila (17.6)", async () => {
    const user = userEvent.setup();
    // El trabajo termina con preguntas: la pantalla se queda y la fila se puede mirar.
    const finished = jobWith({ status: "done", agent_id: AGENT, progress: { step: "writing", blocks: ALL_BLOCKS }, result: RESULT });
    screenWith({ poll: vi.fn(async () => ({ ok: true as const, data: finished })) });
    await describeAgent(user);
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));
    const link = await screen.findByRole("link", { name: "Conectar Stripe" });
    expect(link).toHaveAttribute("href", `/clients/${REF}/integrations`);
    const row = link.closest("[data-slot=builder-skill]") as HTMLElement;
    expect(within(row).getByText("Stripe")).toBeVisible();
    expect(within(row).getByText("Para cobrar con enlace")).toBeVisible();
    // La habilidad que no necesita nada no lleva botón.
    const reservas = screen.getByText("Reservas").closest("[data-slot=builder-skill]") as HTMLElement;
    expect(within(reservas).queryByRole("link")).toBeNull();
  });
});

describe("«Nuevo agente» · las preguntas (17.4, 17.5)", () => {
  async function done(user: ReturnType<typeof userEvent.setup>, answer?: Actions["answer"]) {
    const finished = jobWith({ status: "done", agent_id: AGENT, progress: { step: "writing", blocks: ALL_BLOCKS }, result: RESULT });
    const view = screenWith({ poll: vi.fn(async () => ({ ok: true as const, data: finished })), ...(answer ? { answer } : {}) });
    await describeAgent(user);
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));
    await screen.findByRole("form", { name: "Lo que falta para terminarlo" });
    return view;
  }

  it("cada pregunta dice su porqué y dónde se guarda, y las descartadas dicen por qué", async () => {
    const user = userEvent.setup();
    const { container } = await done(user);
    const business = container.querySelector("[data-question=cancelacion]") as HTMLElement;
    expect(within(business).getByText("Por qué: El agente lo dirá al confirmar cada cita.")).toBeVisible();
    expect(within(business).getByText("Se guarda en la ficha: lo usarán todos sus agentes.")).toBeVisible();
    expect(within(business).getByRole("radio", { name: "24 horas antes" })).toBeVisible();
    await user.click(within(business).getByRole("checkbox", { name: "Solo este agente" }));
    expect(within(business).getByText("Se guarda solo en este agente.")).toBeVisible();

    const agent = container.querySelector("[data-question=saludo]") as HTMLElement;
    expect(within(agent).getByText("Se guarda solo en este agente.")).toBeVisible();
    expect(within(agent).queryByRole("checkbox")).toBeNull();

    const discarded = container.querySelector("[data-slot=builder-discarded]") as HTMLElement;
    expect(within(discarded).getByText("Se descartaron 2 preguntas:")).toBeVisible();
    expect(within(discarded).getByText("Ya estaba en la ficha del negocio.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("manda solo lo respondido, cada respuesta con su `scope`, y va al agente", async () => {
    const user = userEvent.setup();
    const answer = vi.fn(async () => ({ ok: true as const, data: { applied: [], agent_id: AGENT, draft_revision: 3, tests_stale: 8 } }));
    const { container } = await done(user, answer);
    const business = container.querySelector("[data-question=cancelacion]") as HTMLElement;
    await user.click(within(business).getByRole("radio", { name: "2 horas antes" }));
    await user.click(screen.getByRole("button", { name: "Guardar respuestas" }));
    expect(answer).toHaveBeenLastCalledWith({
      ref: REF,
      job: JOB,
      answers: [{ question_id: "cancelacion", value: "2 horas antes", scope: "business" }],
    });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`));

    await user.click(within(business).getByRole("checkbox", { name: "Solo este agente" }));
    const agent = container.querySelector("[data-question=saludo]") as HTMLElement;
    await user.type(within(agent).getByRole("textbox", { name: "Tu respuesta" }), "¡Hola! Soy Recepción.");
    await user.click(screen.getByRole("button", { name: "Guardar respuestas" }));
    expect(answer).toHaveBeenLastCalledWith({
      ref: REF,
      job: JOB,
      answers: [
        { question_id: "cancelacion", value: "2 horas antes", scope: "agent" },
        { question_id: "saludo", value: "¡Hola! Soy Recepción.", scope: "agent" },
      ],
    });
  });

  it("sin respuestas no se manda nada, y se puede seguir sin responder", async () => {
    const user = userEvent.setup();
    const answer = vi.fn();
    await done(user, answer);
    await user.click(screen.getByRole("button", { name: "Guardar respuestas" }));
    expect(answer).not.toHaveBeenCalled();
    expect(screen.getByText("Responde al menos una pregunta o sigue sin responder.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Seguir sin responder" }));
    expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`);
  });
});

describe("«Nuevo agente» · las alternativas (17.8, 17.9, 15.8)", () => {
  it("sin constructor: ofrece plantilla y blanco y no pierde lo escrito", async () => {
    const user = userEvent.setup();
    const failed = jobWith({
      status: "failed",
      error_code: "builder_unavailable",
      progress: { step: "writing", blocks: [], input: { name: NAME, description: DESCRIPTION } },
    });
    const start = vi
      .fn<Actions["start"]>()
      .mockResolvedValueOnce({ ok: true, data: { job_id: JOB, status: "queued", agent_id: null } })
      .mockResolvedValueOnce({ ok: true, data: { job_id: "33333333-3333-4333-8333-333333333333", status: "done", agent_id: AGENT } });
    const { container } = screenWith({ start, poll: vi.fn(async () => ({ ok: true as const, data: failed })) });
    await describeAgent(user);
    await user.click(screen.getByRole("button", { name: "Generar borrador" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("El constructor no ha respondido")).toBeVisible();
    expect(within(alert).getByText(/Lo que escribiste sigue aquí/)).toBeVisible();
    expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue(NAME);
    expect(screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveValue(DESCRIPTION);

    // Las plantillas se abren solas, la del partner primero y sin elegir.
    const picker = container.querySelector("[data-slot=builder-templates]") as HTMLElement;
    const radios = within(picker).getAllByRole("radio");
    expect(radios[0]).toHaveAccessibleName("Barbería · la de tu equipo");
    expect(radios.every((r) => !(r as HTMLInputElement).checked)).toBe(true);
    expect(within(picker).getByRole("group", { name: "Salud" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Crear desde esta plantilla" }));
    expect(screen.getByText("Elige una plantilla.")).toBeVisible();
    expect(start).toHaveBeenCalledTimes(1);

    await user.click(within(picker).getByRole("radio", { name: "Clínica" }));
    await user.click(screen.getByRole("button", { name: "Crear desde esta plantilla" }));
    expect(start).toHaveBeenLastCalledWith({ ref: REF, name: NAME, start: "template", description: DESCRIPTION, template_id: "clinic_v1" });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`));
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«En blanco» crea el agente con el nombre y va a él", async () => {
    const user = userEvent.setup();
    const start = vi.fn(async () => ({ ok: true as const, data: { job_id: JOB, status: "done" as const, agent_id: AGENT } }));
    screenWith({ start });
    await user.type(screen.getByRole("textbox", { name: /Nombre/ }), "Ventas");
    await user.click(screen.getByRole("button", { name: "En blanco" }));
    expect(start).toHaveBeenCalledWith({ ref: REF, name: "Ventas", start: "blank" });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`));
  });

  it("sin plantillas que leer lo dice donde iban", async () => {
    const user = userEvent.setup();
    screenWith({}, null);
    await user.click(screen.getByRole("button", { name: "Empezar desde una plantilla" }));
    expect(screen.getByText("No pudimos cargar las plantillas. Empieza describiéndolo o en blanco.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Crear desde esta plantilla" })).toBeNull();
  });
});
