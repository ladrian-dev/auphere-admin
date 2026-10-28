import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { BuilderBlock, DraftJob, DraftJobResult, DraftOptions } from "@/lib/backend/builder-types";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => nav }));
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
 * «Nuevo agente» como el prototipo aprobado (`agente.md` §3, hueco H7; el
 * owner, 2026-10-28: «no se parece al prototipo»): la misma pantalla del agente
 * —«Nuevo agente», «Borrador · de {cliente}», sus pestañas, dos columnas y la
 * barra de vidrio— con la descripción a la izquierda (nombre, «¿Qué tiene que
 * hacer?» y cuatro ejemplos que la rellenan) y «Probar el agente · Aún no» a la
 * derecha. «Generar borrador» espera a que haya nombre y una frase.
 *
 * Al generar, cuatro pasos que siguen al trabajo de verdad (leer la ficha,
 * proponer, escribir las pruebas, validar las preguntas). Al terminar, la
 * pantalla del agente; si faltan datos, con las preguntas encima (`?job=`).
 * Si el borrador no se puede escribir, la plantilla y el blanco, sin perder lo
 * escrito. Nunca se nombra al constructor.
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
    answer: vi.fn(),
    ...actions,
  };
  const view = render(
    <LocaleProvider locale="es">
      <BuilderNew
        refId={REF}
        clientName="Barbería Cultor"
        options={options}
        actions={full}
        wait={() => new Promise((resolve) => setTimeout(resolve, 0))}
      />
    </LocaleProvider>,
  );
  return { ...view, actions: full };
}

const nameBox = () => screen.getByRole("textbox", { name: /Nombre/ });
const descriptionBox = () => screen.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ });
const bar = () => screen.getByRole("region", { name: "Acciones del agente" });
const generate = () => within(bar()).getByRole("button", { name: "Generar borrador" });

async function describeAgent(user: ReturnType<typeof userEvent.setup>) {
  await user.type(nameBox(), NAME);
  await user.type(descriptionBox(), DESCRIPTION);
}

/** El estado de cada paso de «Cómo va el borrador», en orden. */
const stepStates = () =>
  within(screen.getByRole("list", { name: "Cómo va el borrador" }))
    .getAllByRole("listitem")
    .map((li) => li.getAttribute("data-state"));

beforeEach(() => {
  nav.push.mockClear();
  toast.success.mockClear();
});

describe("«Nuevo agente» · describir (§3.1)", () => {
  it("es la pantalla del agente: título, «Borrador · de {cliente}», pestañas, la descripción y «Aún no»; pasa axe", async () => {
    const { container } = screenWith({});
    expect(screen.getByRole("heading", { level: 1, name: "Nuevo agente" })).toBeVisible();
    expect(screen.getByText("Borrador")).toBeVisible();
    expect(screen.getByText("de Barbería Cultor")).toBeVisible();
    const tabs = screen.getByRole("tablist", { name: "Secciones del agente" });
    expect(within(tabs).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Configuración", "Canales", "Conectores"]);
    expect(within(tabs).getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
    expect(within(tabs).getByRole("tab", { name: /Canales/ })).toHaveAttribute("aria-disabled", "true");

    const describe = screen.getByRole("region", { name: "Describe el agente" });
    expect(within(describe).getByRole("textbox", { name: /Nombre/ })).toHaveAttribute("maxLength", "40");
    expect(within(describe).getByRole("textbox", { name: /Nombre/ })).toHaveAttribute("placeholder", "Recepción");
    expect(within(describe).getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveAttribute("maxLength", "1024");
    expect(within(describe).getByRole("group", { name: "Empieza con un ejemplo:" })).toBeVisible();
    // Como el prototipo: sin contadores.
    expect(screen.queryByText("0 de 40")).toBeNull();

    const tryIt = screen.getByRole("region", { name: "Probar el agente" });
    expect(within(tryIt).getByText("Aún no")).toBeVisible();
    expect(within(tryIt).getByText("Disponible en cuanto generes el borrador y le pongas sus parámetros.")).toBeVisible();
    expect(within(tryIt).getByText("Chat simulado con agenda y hora de prueba. Nada llega a clientes reales.")).toBeVisible();

    expect(bar().closest("[data-slot=agent-actionbar]")?.className).toMatch(/(^|\s)glass(\s|$)/);
    expect(within(bar()).getByRole("status")).toHaveTextContent("Nombre y una descripción de al menos una frase");
    expect(generate()).toBeDisabled();
    expect(document.body.textContent).not.toMatch(/constructor/i);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Generar borrador» se habilita con un nombre y una frase", async () => {
    const user = userEvent.setup();
    screenWith({});
    await user.type(nameBox(), NAME);
    expect(generate()).toBeDisabled();
    await user.type(descriptionBox(), "Muy corta");
    expect(generate()).toBeDisabled();
    await user.clear(descriptionBox());
    await user.type(descriptionBox(), DESCRIPTION);
    expect(within(bar()).getByRole("status")).toHaveTextContent("Listo para generar el borrador");
    expect(generate()).toBeEnabled();
  });

  it("un ejemplo rellena la descripción con un texto general y el nombre si estaba vacío", async () => {
    const user = userEvent.setup();
    screenWith({});
    const examples = screen.getByRole("group", { name: "Empieza con un ejemplo:" });
    expect(within(examples).getAllByRole("button").map((b) => b.textContent)).toEqual(["Recepción y citas", "Ventas", "Soporte", "Cobros"]);
    await user.click(within(examples).getByRole("button", { name: "Recepción y citas" }));
    expect(nameBox()).toHaveValue("Recepción");
    expect((descriptionBox() as HTMLTextAreaElement).value).toMatch(/^Atiende el WhatsApp del negocio: da citas/);
    expect(generate()).toBeEnabled();
    // Un nombre escrito no se pisa; la descripción se sustituye.
    await user.clear(nameBox());
    await user.type(nameBox(), "Mostrador");
    await user.click(within(examples).getByRole("button", { name: "Cobros" }));
    expect(nameBox()).toHaveValue("Mostrador");
    expect((descriptionBox() as HTMLTextAreaElement).value).toMatch(/^Recuerda los pagos pendientes/);
    // Textos generales: ni negocios ni personas concretas.
    expect((descriptionBox() as HTMLTextAreaElement).value).not.toMatch(/Marta|barber|clínica/i);
  });

  it("«Crear este agente» del cliente llega con su nombre y su descripción (18.4)", () => {
    render(
      <LocaleProvider locale="es">
        <BuilderNew refId={REF} options={OPTIONS} initial={{ name: NAME, description: DESCRIPTION }} actions={{ start: vi.fn(), poll: vi.fn(), answer: vi.fn() }} />
      </LocaleProvider>,
    );
    expect(nameBox()).toHaveValue(NAME);
    expect(descriptionBox()).toHaveValue(DESCRIPTION);
  });

  it("un nombre ocupado se dice en el nombre", async () => {
    const user = userEvent.setup();
    screenWith({ start: vi.fn(async () => ({ ok: false as const, status: 409, message: "", code: "name_taken" })) });
    await describeAgent(user);
    await user.click(generate());
    expect(await screen.findByText("Ya hay un agente con ese nombre en este cliente. Elige otro.")).toBeVisible();
    expect(nameBox()).toHaveValue(NAME);
  });
});

describe("«Nuevo agente» · preparando el borrador (§3.2)", () => {
  it("los cuatro pasos siguen al trabajo y, con preguntas, va a la pantalla del agente con ellas", async () => {
    const user = userEvent.setup();
    const { poll, release } = gatedPoll([
      jobWith({ progress: { step: "reading", blocks: [] } }),
      jobWith({ progress: { step: "writing", blocks: ALL_BLOCKS.slice(0, 2) } }),
      jobWith({ progress: { step: "writing", blocks: ALL_BLOCKS.slice(0, 9) } }),
      jobWith({ status: "done", agent_id: AGENT, progress: { step: "writing", blocks: ALL_BLOCKS }, result: RESULT }),
    ]);
    const { actions, container } = screenWith({ poll });
    await describeAgent(user);
    await user.click(generate());
    expect(actions.start).toHaveBeenCalledWith({ ref: REF, name: NAME, description: DESCRIPTION, start: "describe" });

    // La cabecera ya dice su nombre; la barra, que se prepara, sin botones.
    expect(await screen.findByRole("heading", { level: 1, name: NAME })).toBeVisible();
    expect(within(bar()).getByRole("status")).toHaveTextContent("Preparando el borrador…");
    expect(within(bar()).queryByRole("button")).toBeNull();
    expect(within(screen.getByRole("region", { name: "Probar el agente" })).getByText("Preparando el borrador…")).toBeVisible();
    const steps = screen.getByRole("list", { name: "Cómo va el borrador" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.querySelector("[data-slot=step-text]")?.textContent)).toEqual([
      "Leo la ficha de Barbería Cultor como datos, nunca como permisos",
      "Propongo instrucciones y habilidades",
      "Escribo las pruebas del caso y sumo las del sector",
      "Valido qué preguntas hacen falta de verdad",
    ]);
    expect(stepStates()).toEqual(["active", "wait", "wait", "wait"]);

    await release();
    expect(stepStates()).toEqual(["active", "wait", "wait", "wait"]);
    await release();
    await waitFor(() => expect(stepStates()).toEqual(["done", "active", "wait", "wait"]));
    await release();
    await waitFor(() => expect(stepStates()).toEqual(["done", "done", "active", "wait"]));
    // El número sale del trabajo, no es fijo.
    expect(within(steps).getByText("Escribo 8 pruebas del caso y sumo las del sector")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);

    await release();
    await waitFor(() => expect(stepStates()).toEqual(["done", "done", "done", "done"]));
    expect(poll).toHaveBeenCalledWith({ ref: REF, job: JOB });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}?job=${JOB}`));
  });

  it("sin preguntas, va a la pantalla del agente sin más", async () => {
    const user = userEvent.setup();
    const finished = jobWith({
      status: "done",
      agent_id: AGENT,
      progress: { step: "writing", blocks: ALL_BLOCKS },
      result: { ...RESULT, questions: [], discarded: { count: 0, reasons: [] } },
    });
    screenWith({ poll: vi.fn(async () => ({ ok: true as const, data: finished })) });
    await describeAgent(user);
    await user.click(generate());
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}`));
  });
});

describe("«Nuevo agente» · otras formas de empezar (17.8, 17.9, 15.8)", () => {
  it("si el borrador no se puede escribir: lo dice, no pierde lo escrito y ofrece las plantillas", async () => {
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
    await user.click(generate());

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("No se pudo escribir el borrador")).toBeVisible();
    expect(within(alert).getByText(/Lo que escribiste sigue aquí/)).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Nuevo agente" })).toBeVisible();
    expect(nameBox()).toHaveValue(NAME);
    expect(descriptionBox()).toHaveValue(DESCRIPTION);

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

  it("«En blanco», discreto bajo los ejemplos, crea el agente con el nombre y va a él", async () => {
    const user = userEvent.setup();
    const start = vi.fn(async () => ({ ok: true as const, data: { job_id: JOB, status: "done" as const, agent_id: AGENT } }));
    screenWith({ start });
    const other = document.querySelector("[data-slot=builder-alternatives]") as HTMLElement;
    expect(within(other).getByText("Otras formas de empezar:")).toBeVisible();
    await user.type(nameBox(), "Ventas");
    await user.click(within(other).getByRole("button", { name: "En blanco" }));
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
