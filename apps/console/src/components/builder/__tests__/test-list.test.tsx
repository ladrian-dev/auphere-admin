import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { AGENT, JOB, REF, TESTS, fail, job, noWait, ok, suite } from "./quality-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({
  addTestAction: vi.fn(),
  qualityJobAction: vi.fn(),
  runTestsAction: vi.fn(),
  setNotApplicableAction: vi.fn(),
  testsAction: vi.fn(),
}));

const { TestList } = await import("../test-list");
type Actions = NonNullable<React.ComponentProps<typeof TestList>["actions"]>;

/**
 * Spec 047 (historia 8, T089; requisito 21) — la lista de pruebas: por tipo,
 * con su estado («Pasa», «Inestable», «Falla», «No sé», «Sin ejecutar», «No
 * aplica», «Desactualizada»), «Por qué falló» con lo que se comprobó,
 * «Arreglar», «No aplica» con su razón para las del sector, ejecutar como un
 * trabajo y el aviso del juez sin calibrar.
 */

function screenWith(props: Partial<React.ComponentProps<typeof TestList>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    load: vi.fn(async () => ok(suite())),
    run: vi.fn(async () => ok({ job_id: JOB, run_id: "r1", tests: 5 })),
    poll: vi.fn(async () => ok(job({ kind: "tests", status: "done" }))),
    notApplicable: vi.fn(async () => ok(suite())),
    add: vi.fn(async () => ok(suite())),
    ...actions,
  };
  const onFix = vi.fn();
  const onChanged = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <TestList refId={REF} agentId={AGENT} suite={suite()} canWrite onFix={onFix} onChanged={onChanged} actions={full} wait={noWait} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full, onFix, onChanged };
}

const row = (name: string) => screen.getByRole("listitem", { name }) as HTMLElement;

beforeEach(() => toast.success.mockClear());

describe("la lista de pruebas (21.5)", () => {
  it("las agrupa por tipo y dice el estado de cada una, y pasa axe", async () => {
    const { container } = screenWith();
    expect(screen.getByRole("heading", { name: "Del caso · 3" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Del sector · 2" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Añadidas por tu equipo · 1" })).toBeVisible();
    expect(within(row("Pregunta el horario")).getByText("Pasa")).toBeVisible();
    expect(within(row("Reserva una cita")).getByText("Falla")).toBeVisible();
    expect(within(row("Reserva una cita")).getByText("Crítica")).toBeVisible();
    expect(within(row("Pide un descuento")).getByText("Inestable")).toBeVisible();
    expect(within(row("Pide un descuento")).getByText("Desactualizada")).toBeVisible();
    expect(within(row("Pide un descuento")).getByText("2 de 3 repeticiones")).toBeVisible();
    expect(within(row("Pregunta por aparcamiento")).getByText("Sin ejecutar")).toBeVisible();
    expect(within(row("Pide cita para un perro")).getByText("No aplica")).toBeVisible();
    expect(within(row("Pide cita para un perro")).getByText("No aplica: No atendemos mascotas")).toBeVisible();
    expect(within(row("Pregunta por la tarjeta regalo")).getByText("No sé")).toBeVisible();
    expect(screen.getByText("1 de 5 pasan")).toBeVisible();
    expect(screen.queryByText(/El juez aún no decide/)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Por qué falló» enseña lo que se comprobó y «Arreglar» abre el borrador", async () => {
    const user = userEvent.setup();
    const { onFix } = screenWith();
    const failing = row("Reserva una cita");
    await user.click(within(failing).getByText("Por qué falló"));
    expect(within(failing).getByText("La cita no existe en la agenda al terminar.")).toBeVisible();
    await user.click(within(failing).getByRole("button", { name: "Arreglar Reserva una cita en las instrucciones" }));
    expect(onFix).toHaveBeenCalledWith(expect.objectContaining({ name: "Reserva una cita" }));
    // La que pasa no trae «Por qué falló» ni «Arreglar».
    expect(within(row("Pregunta el horario")).queryByText("Por qué falló")).toBeNull();
    expect(within(row("Pregunta el horario")).queryByRole("button", { name: /Arreglar/ })).toBeNull();
  });

  it("una del sector se marca «No aplica» con su razón, y vuelve a aplicar", async () => {
    const user = userEvent.setup();
    const { actions, onChanged } = screenWith();
    const parking = row("Pregunta por aparcamiento");
    // Solo las del sector: las del caso no lo ofrecen.
    expect(within(row("Pregunta el horario")).queryByRole("button", { name: /No aplica/ })).toBeNull();
    await user.click(within(parking).getByRole("button", { name: "Marcar Pregunta por aparcamiento como «No aplica»" }));
    const form = screen.getByRole("form", { name: "Marcar Pregunta por aparcamiento como «No aplica»" });
    await user.type(within(form).getByRole("textbox", { name: /Por qué no aplica/ }), "no");
    await user.click(within(form).getByRole("button", { name: "Guardar la razón" }));
    expect(within(form).getByText("Escribe la razón, con al menos 3 caracteres.")).toBeVisible();
    expect(actions.notApplicable).not.toHaveBeenCalled();
    await user.type(within(form).getByRole("textbox", { name: /Por qué no aplica/ }), " hay aparcamiento: es online");
    await user.click(within(form).getByRole("button", { name: "Guardar la razón" }));
    expect(actions.notApplicable).toHaveBeenCalledWith({ ref: REF, agent: AGENT, test: TESTS[3]!.id, reason: "no hay aparcamiento: es online" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());

    await user.click(within(row("Pide cita para un perro")).getByRole("button", { name: "Vuelve a aplicar" }));
    expect(actions.notApplicable).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, test: TESTS[4]!.id, reason: "" });
  });

  it("«Ejecutar todas» es un trabajo: espera a que termine y vuelve a leer la lista", async () => {
    const user = userEvent.setup();
    const poll = vi.fn<Actions["poll"]>(async () => ok(job({ kind: "tests", status: "done" }))).mockResolvedValueOnce(ok(job({ kind: "tests" })));
    const { actions, onChanged } = screenWith({}, { poll });
    await user.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(actions.run).toHaveBeenCalledWith({ ref: REF, agent: AGENT, scope: "all" });
    await waitFor(() => expect(actions.load).toHaveBeenCalled());
    expect(poll).toHaveBeenCalledWith({ ref: REF, job: JOB });
    expect(onChanged).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Pruebas terminadas.");

    await user.click(screen.getByRole("button", { name: "Ejecutar las desactualizadas" }));
    expect(actions.run).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, scope: "affected" });
    await waitFor(() => expect(actions.load).toHaveBeenCalledTimes(2));
    await user.click(within(row("Reserva una cita")).getByRole("button", { name: "Ejecutar Reserva una cita" }));
    expect(actions.run).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, scope: "one", test: TESTS[1]!.id });
  });

  it("dice por qué no se pudo ejecutar", async () => {
    const user = userEvent.setup();
    screenWith({}, { run: vi.fn(async () => fail(409, "nothing_to_run")) });
    await user.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("No hay ninguna prueba que ejecutar.")).toBeVisible();
  });

  it("sin el juez calibrado lo dice, y quien solo lee no ve botones", () => {
    screenWith({ suite: suite({ judge_calibrated: false, allowed: [] }), canWrite: false });
    expect(screen.getByText("El juez aún no decide: solo cuenta el estado final.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Ejecutar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /No aplica|Arreglar|Añadir/ })).toBeNull();
    // «Por qué falló» sí se ve: leer no es escribir.
    expect(within(row("Reserva una cita")).getByText("Por qué falló")).toBeVisible();
  });

  it("añade una prueba con su primer mensaje", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith();
    await user.click(screen.getByRole("button", { name: "Añadir una prueba" }));
    const form = screen.getByRole("form", { name: "Añadir una prueba" });
    await user.type(within(form).getByRole("textbox", { name: /Nombre de la prueba/ }), "Pide factura");
    await user.type(within(form).getByRole("textbox", { name: /Primer mensaje/ }), "¿Me hacéis factura?");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Añadir" }));
    expect(actions.add).toHaveBeenCalledWith({ ref: REF, agent: AGENT, test: { name: "Pide factura", first_message: "¿Me hacéis factura?", critical: true } });
  });
});

/**
 * Spec 047, enmienda del 2026-10-30 (T228; requisitos 65.8 y 65.9;
 * `contracts/console-api.md` §11): una prueba del sector que pide lo que el
 * agente no tiene llega ya «No aplica», con su razón, sin que nadie la marque.
 * Se ve como «No aplica» y se reactiva como hoy. Un agente estructurado sin
 * ninguna prueba que le aplique no se guarda: la lista lo dice.
 */
describe("la lista de pruebas · solo lo que tenemos (65.8, 65.9)", () => {
  const AUTO = TESTS.map((x) =>
    x.name === "Pide cita para un perro" ? { ...x, not_applicable_reason: "No aplica: este agente no tiene herramienta para reservar citas." } : x,
  );

  it("la que llega «No aplica» se ve así, con su razón y sin repetir «No aplica»", async () => {
    const { container } = screenWith({ suite: suite({ tests: AUTO }) });
    const dog = row("Pide cita para un perro");
    expect(within(dog).getByText("No aplica")).toBeVisible();
    expect(within(dog).getByText("No aplica: este agente no tiene herramienta para reservar citas.")).toBeVisible();
    expect(within(dog).queryByText(/No aplica: No aplica/)).toBeNull();
    expect(within(dog).queryByRole("button", { name: /Ejecutar/ })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Vuelve a aplicar» no se pulsa dos veces y, si no se puede, lo dice en su fila", async () => {
    const user = userEvent.setup();
    let answer: (value: ReturnType<typeof fail>) => void = () => undefined;
    const notApplicable = vi.fn<Actions["notApplicable"]>(() => new Promise((resolve) => (answer = resolve)));
    screenWith({ suite: suite({ tests: AUTO }) }, { notApplicable });
    const dog = row("Pide cita para un perro");
    const again = within(dog).getByRole("button", { name: "Vuelve a aplicar" });
    await user.click(again);
    expect(again).toBeDisabled();
    await user.click(again);
    expect(notApplicable).toHaveBeenCalledTimes(1);
    expect(notApplicable).toHaveBeenCalledWith({ ref: REF, agent: AGENT, test: TESTS[4]!.id, reason: "" });
    answer(fail(500));
    expect(await within(dog).findByRole("alert")).toHaveTextContent("No se pudo volver a activar. Inténtalo de nuevo.");
    expect(within(dog).getByRole("button", { name: "Vuelve a aplicar" })).toBeEnabled();
  });

  it("un estructurado sin ninguna prueba que le aplique lo dice; con alguna, o uno de antes, no", () => {
    const none = suite({
      summary: { passed: 0, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 1, total: 1, stale: 0, critical_failed: [], rate: null },
      tests: [AUTO[4]!],
    });
    const { unmount } = screenWith({ suite: none, structured: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Ninguna prueba aplica a este agente. Añade una que le aplique: sin ella no se puede guardar.");
    expect(screen.getByRole("button", { name: "Añadir una prueba" })).toBeVisible();
    unmount();
    const empty = screenWith({ suite: suite({ summary: { ...none.summary, not_applicable: 0, total: 0 }, tests: [] }), structured: true });
    expect(screen.getByText(/Ninguna prueba aplica a este agente/)).toBeVisible();
    empty.unmount();
    const other = screenWith({ suite: none, structured: false });
    expect(screen.queryByText(/Ninguna prueba aplica a este agente/)).toBeNull();
    other.unmount();
    screenWith({ structured: true });
    expect(screen.queryByText(/Ninguna prueba aplica a este agente/)).toBeNull();
  });

  it("«Añadir una prueba» se puede abrir desde fuera (la puerta), con el foco en su primer campo", () => {
    const { rerender } = screenWith();
    expect(screen.queryByRole("form", { name: "Añadir una prueba" })).toBeNull();
    rerender(
      <LocaleProvider locale="es">
        <TestList refId={REF} agentId={AGENT} suite={suite()} canWrite actions={{} as Actions} wait={noWait} addRequest={1} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("form", { name: "Añadir una prueba" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: /Nombre de la prueba/ })).toHaveFocus();
  });
});
