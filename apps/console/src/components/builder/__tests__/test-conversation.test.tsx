import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentTest, TestTurn } from "@/lib/backend/agent-quality-types";

import { AGENT, JOB, REF, TESTS, job, noWait, ok, suite, test } from "./quality-fixtures";

vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({
  addTestAction: vi.fn(),
  qualityJobAction: vi.fn(),
  runTestsAction: vi.fn(),
  setNotApplicableAction: vi.fn(),
  testsAction: vi.fn(),
}));

const { TestList } = await import("../test-list");
const { TestsBox } = await import("../tests-box");
const { TestConversation } = await import("../test-conversation");
const { failedConversation, isGenerated } = await import("../quality-model");

/**
 * Spec 047, enmienda del 2026-10-29 (T215; requisitos 58.4 y 61.6) — «Por qué
 * falló» enseña la conversación de la prueba con el cliente simulado, turno a
 * turno (las burbujas del chat de prueba: el cliente a la derecha, el agente a
 * la izquierda, y lo que habría hecho como «Lo que habría hecho: …»), y por qué
 * terminó. Las pruebas de una guía generada para el cliente llevan «Generada».
 */

const TRANSCRIPT: TestTurn[] = [
  { role: "customer", text: "Hola, quiero cita mañana a las 10", actions: [] },
  { role: "agent", text: "¡Hola! Mañana a las 10 tengo hueco. ¿Para qué servicio?", actions: ["buscar huecos libres mañana"] },
  { role: "customer", text: "Corte de pelo", actions: [] },
  { role: "agent", text: "Perfecto, te lo apunto.", actions: [] },
];

const failing = (over: Partial<AgentTest> = {}): AgentTest =>
  test({
    id: "77777777-7777-4777-8777-000000000002",
    name: "Reserva una cita",
    critical: true,
    status: "failed",
    passes: 0,
    decided: 3,
    why_failed: "La cita no existe en la agenda al terminar.",
    transcript: TRANSCRIPT,
    stop: "turn_limit",
    ...over,
  });

function list(tests: AgentTest[]) {
  return render(
    <LocaleProvider locale="es">
      <TestList
        refId={REF}
        agentId={AGENT}
        suite={suite({ tests })}
        canWrite
        actions={{
          load: vi.fn(async () => ok(suite({ tests }))),
          run: vi.fn(async () => ok({ job_id: JOB, run_id: "r1", tests: 1 })),
          poll: vi.fn(async () => ok(job({ kind: "tests", status: "done" }))),
          notApplicable: vi.fn(async () => ok(suite({ tests }))),
          add: vi.fn(async () => ok(suite({ tests }))),
        }}
        wait={noWait}
      />
    </LocaleProvider>,
  );
}

const row = (name: string) => screen.getByRole("listitem", { name }) as HTMLElement;

describe("«Por qué falló», turno a turno (61.6)", () => {
  it("enseña lo comprobado, la conversación con burbujas y lo que habría hecho, y por qué terminó; pasa axe", async () => {
    const user = userEvent.setup();
    const { container } = list([TESTS[0]!, failing()]);
    const failingRow = row("Reserva una cita");
    await user.click(within(failingRow).getByText("Por qué falló"));
    expect(within(failingRow).getByText("La cita no existe en la agenda al terminar.")).toBeVisible();
    const chat = within(failingRow).getByRole("list", { name: "La conversación de la prueba" });
    const turns = within(chat).getAllByRole("listitem").filter((li) => li.dataset.slot === "test-turn");
    expect(turns.map((li) => li.dataset.role)).toEqual(["customer", "agent", "customer", "agent"]);
    // Quién habla, para los lectores de pantalla; el cliente a la derecha, como en el chat de prueba.
    expect(within(turns[0]!).getByText("Cliente simulado")).toHaveClass("sr-only");
    expect(turns[0]!.className).toMatch(/items-end/);
    expect(turns[1]!.className).toMatch(/items-start/);
    expect(within(turns[1]!).getByText("Lo que habría hecho: buscar huecos libres mañana")).toBeVisible();
    expect(within(failingRow).getByText("Llegó a 8 turnos del cliente sin cumplir el plan.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin conversación guardada (pruebas de antes), solo lo comprobado", async () => {
    const user = userEvent.setup();
    list([failing({ transcript: undefined, stop: undefined })]);
    const failingRow = row("Reserva una cita");
    await user.click(within(failingRow).getByText("Por qué falló"));
    expect(within(failingRow).getByText("La cita no existe en la agenda al terminar.")).toBeVisible();
    expect(within(failingRow).queryByRole("list", { name: "La conversación de la prueba" })).toBeNull();
  });

  it("la tarjeta de pruebas deja ver la conversación de la que falla", async () => {
    const user = userEvent.setup();
    const t = failing({ stop: "handoff" });
    render(
      <LocaleProvider locale="es">
        <TestsBox
          refId={REF}
          tests={{ suite: suite({ tests: [t] }), running: null, pending: false, error: null, canRun: false, run: vi.fn(), ask: vi.fn(), confirm: null, reload: vi.fn() }}
          review={null}
          canWrite
          onFix={vi.fn()}
          onEdit={vi.fn()}
          onAll={vi.fn()}
        />
      </LocaleProvider>,
    );
    const box = screen.getByRole("alert");
    await user.click(within(box).getByText("Ver la conversación"));
    expect(within(box).getByRole("list", { name: "La conversación de la prueba" })).toBeVisible();
    expect(within(box).getByText("Terminó porque el agente pasó la conversación a una persona.")).toBeVisible();
  });

  it("cada motivo de parada se dice en palabras", () => {
    const stops = { plan_done: "cumplió su plan", goodbye: "se despidió", handoff: "a una persona", turn_limit: "8 turnos" } as const;
    for (const [stop, words] of Object.entries(stops)) {
      const { unmount } = render(
        <LocaleProvider locale="es">
          <TestConversation transcript={TRANSCRIPT} stop={stop as keyof typeof stops} />
        </LocaleProvider>,
      );
      expect(screen.getByText(new RegExp(words))).toBeVisible();
      unmount();
    }
  });

  it("un texto largo se parte en la burbuja sin desbordar", () => {
    const long = "Quiero-una-cita-para-el-corte-de-pelo-y-el-arreglo-de-barba-".repeat(6);
    render(
      <LocaleProvider locale="es">
        <TestConversation transcript={[{ role: "customer", text: long, actions: [] }]} stop={null} />
      </LocaleProvider>,
    );
    expect(screen.getByText(long).className).toMatch(/break-words/);
  });
});

describe("la conversación que se enseña (modelo)", () => {
  it("la de la prueba si viene; si no, la del primer intento que falló; si no, ninguna", () => {
    expect(failedConversation(failing())).toEqual({ transcript: TRANSCRIPT, stop: "turn_limit" });
    const second: TestTurn[] = [{ role: "customer", text: "Hola", actions: [] }];
    const byAttempt = failing({
      transcript: undefined,
      stop: undefined,
      attempts: [
        { passed: true, transcript: TRANSCRIPT, stop: "plan_done" },
        { passed: false, transcript: second, stop: "goodbye" },
      ],
    });
    expect(failedConversation(byAttempt)).toEqual({ transcript: second, stop: "goodbye" });
    expect(failedConversation(failing({ transcript: [], stop: null }))).toBeNull();
    expect(failedConversation(failing({ transcript: undefined, stop: undefined }))).toBeNull();
  });

  it("un motivo que no conoce no se enseña", () => {
    expect(failedConversation(failing({ stop: "weird" as never }))).toEqual({ transcript: TRANSCRIPT, stop: null });
  });

  it("«Generada» es la prueba con `origin: generated`", () => {
    expect(isGenerated(test({ origin: "generated" }))).toBe(true);
    expect(isGenerated(test({}))).toBe(false);
  });
});

describe("«Generada» en la guía y en sus pruebas (58.4)", () => {
  it("cada prueba generada lo dice, y el grupo del sector explica por qué", () => {
    list([
      test({ id: "a", kind: "sector", name: "Pregunta por la cuota mensual", status: "not_run", origin: "generated" }),
      test({ id: "b", kind: "sector", name: "Pide una clase de prueba", status: "passed", origin: "generated" }),
      test({ id: "c", kind: "case", name: "Pregunta el horario", status: "passed" }),
    ]);
    expect(within(row("Pregunta por la cuota mensual")).getByText("Generada")).toBeVisible();
    expect(within(row("Pide una clase de prueba")).getByText("Generada")).toBeVisible();
    expect(within(row("Pregunta el horario")).queryByText("Generada")).toBeNull();
    expect(screen.getByText("Auphere no tiene guía para este sector: estas pruebas se generaron para este cliente.")).toBeVisible();
  });

  it("con guía de Auphere no dice nada", () => {
    list(TESTS);
    expect(screen.queryByText("Generada")).toBeNull();
    expect(screen.queryByText(/se generaron para este cliente/)).toBeNull();
  });
});

/**
 * Spec 065 (T062; requisitos 5.3 y 6.1) — en la conversación de una prueba, bajo
 * cada respuesta del agente, qué modelo respondió. La transcripción solo trae el
 * id: el nombre sale de los modelos del agente que ya lee la pantalla, y si no
 * está, el id. Si respondió la reserva, se dice.
 */
describe("el modelo que respondió en la prueba (spec 065)", () => {
  const NAMES = { "openai/gpt-5.6-terra": "Terra", "anthropic/claude-sonnet-5-5": "Claude Sonnet 5.5" };
  const WITH_MODELS: TestTurn[] = [
    { role: "customer", text: "Hola, quiero cita mañana a las 10", actions: [] },
    { role: "agent", text: "Mañana a las 10 tengo hueco.", actions: [], model: "openai/gpt-5.6-terra", fell_back: false },
    { role: "customer", text: "Corte de pelo", actions: [] },
    { role: "agent", text: "Perfecto, te lo apunto.", actions: [], model: "anthropic/claude-sonnet-5-5", fell_back: true },
    { role: "customer", text: "Gracias", actions: [] },
    { role: "agent", text: "A ti.", actions: [], model: "openai/gpt-5.6-luna", fell_back: false },
    { role: "customer", text: "Adiós", actions: [] },
    { role: "agent", text: "Hasta pronto.", actions: [] },
  ];

  it("dice el nombre bajo cada respuesta del agente, la reserva cuando lo fue, y el id si no hay nombre", async () => {
    const { container } = render(
      <LocaleProvider locale="es">
        <TestConversation transcript={WITH_MODELS} stop="plan_done" modelNames={NAMES} />
      </LocaleProvider>,
    );
    const turns = screen.getAllByRole("listitem").filter((li) => li.dataset.slot === "test-turn");
    expect(within(turns[1]!).getByText("Respondió Terra")).toBeVisible();
    expect(within(turns[3]!).getByText("Respondió Claude Sonnet 5.5, el modelo de reserva, porque el del agente no contestó.")).toBeVisible();
    expect(within(turns[5]!).getByText("Respondió openai/gpt-5.6-luna")).toBeVisible();
    // Las transcripciones de antes no traen modelo: nada.
    expect(within(turns[7]!).queryByText(/^Respondió /)).toBeNull();
    // Nunca bajo el cliente simulado.
    expect(within(turns[0]!).queryByText(/^Respondió /)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin nombres, el id", () => {
    render(
      <LocaleProvider locale="es">
        <TestConversation transcript={WITH_MODELS.slice(0, 2)} stop={null} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Respondió openai/gpt-5.6-terra")).toBeVisible();
  });

  it("«Por qué falló» y la tarjeta de pruebas lo dicen con los nombres de la pantalla", async () => {
    const user = userEvent.setup();
    const t = failing({ transcript: WITH_MODELS.slice(0, 4) });
    render(
      <LocaleProvider locale="es">
        <TestList
          refId={REF}
          agentId={AGENT}
          suite={suite({ tests: [t] })}
          canWrite
          modelNames={NAMES}
          actions={{
            load: vi.fn(async () => ok(suite({ tests: [t] }))),
            run: vi.fn(async () => ok({ job_id: JOB, run_id: "r1", tests: 1 })),
            poll: vi.fn(async () => ok(job({ kind: "tests", status: "done" }))),
            notApplicable: vi.fn(async () => ok(suite({ tests: [t] }))),
            add: vi.fn(async () => ok(suite({ tests: [t] }))),
          }}
          wait={noWait}
        />
        <TestsBox
          refId={REF}
          tests={{ suite: suite({ tests: [t] }), running: null, pending: false, error: null, canRun: false, run: vi.fn(), ask: vi.fn(), confirm: null, reload: vi.fn() }}
          review={null}
          canWrite
          modelNames={NAMES}
          onFix={vi.fn()}
          onEdit={vi.fn()}
          onAll={vi.fn()}
        />
      </LocaleProvider>,
    );
    const failingRow = row("Reserva una cita");
    await user.click(within(failingRow).getByText("Por qué falló"));
    expect(within(failingRow).getByText("Respondió Terra")).toBeVisible();
    const box = screen.getByRole("alert");
    await user.click(within(box).getByText("Ver la conversación"));
    expect(within(box).getByText("Respondió Claude Sonnet 5.5, el modelo de reserva, porque el del agente no contestó.")).toBeVisible();
  });
});
