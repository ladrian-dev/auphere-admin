import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { REF, TESTS, suite } from "./quality-fixtures";

vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({
  qualityJobAction: vi.fn(),
  runTestsAction: vi.fn(),
  testsAction: vi.fn(),
}));

const { TestsBox } = await import("../tests-box");
type Tests = React.ComponentProps<typeof TestsBox>["tests"];

/**
 * La tarjeta de pruebas cuando un modelo no respondió (bug
 * `el-probador-tapa-los-fallos-del-modelo`): lo dice, no se lo apunta al agente y solo
 * pide repetirlas a quien puede.
 */
const untested = suite({
  tests: [{ ...TESTS[0]!, status: "model_failed", passes: 0, decided: 0, stale: true, why_failed: null, why_untested: "El modelo del agente no respondió.", name: "Sin modelo" }],
  summary: { ...suite().summary, passed: 0, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 0, total: 1, stale: 1, model_failed: 1, critical_failed: [], rate: null },
});

function box(over: Partial<Tests> = {}, canWrite = true) {
  const tests: Tests = { suite: untested, running: null, pending: false, error: null, canRun: canWrite, run: vi.fn(), ask: vi.fn(), confirm: null, reload: vi.fn(), ...over };
  return render(
    <LocaleProvider locale="es">
      <TestsBox refId={REF} tests={tests} review={null} canWrite={canWrite} onFix={vi.fn()} onEdit={vi.fn()} onAll={vi.fn()} />
    </LocaleProvider>,
  );
}

describe("la tarjeta de pruebas, sin modelo", () => {
  it("dice cuántas no se pudieron probar y que no es culpa del agente, sin «Arreglar»", async () => {
    const { container } = box();
    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("Sin probar porque el modelo no respondió: 1. Esto no dice nada del agente. Vuelve a ejecutarlas en un rato.");
    expect(within(container).queryByRole("button", { name: /Arreglar/ })).toBeNull();
    expect(within(container).getByRole("button", { name: "Ejecutar todas" })).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("a quien solo lee no le pide que las ejecute", () => {
    box({}, false);
    expect(screen.getByRole("alert")).toHaveTextContent("Sin probar porque el modelo no respondió: 1. Esto no dice nada del agente.");
    expect(screen.queryByText(/Vuelve a ejecutar/)).toBeNull();
  });

  it("con el error de la pasada a la vista no lo repite, ni mientras corre otra", () => {
    const { unmount } = box({ error: "No se pudo probar: ningún modelo respondió." });
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    unmount();
    box({ running: { count: 1 } });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("la tarjeta de pruebas, sin decidir (66.6)", () => {
  const unknown = { ...TESTS[0]!, name: "Pregunta el precio", status: "unknown" as const, stale: false, critical: true, why_failed: null };
  const failed = { ...TESTS[0]!, name: "Reserva una cita", status: "failed" as const, stale: false, critical: false };

  it("«No sé» no se llama fallo ni ofrece «Arreglar»", () => {
    box({ suite: suite({ tests: [unknown] }) });
    expect(screen.getByText("Sin decidir: «Pregunta el precio»")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Arreglar/ })).toBeNull();
  });

  it("lo que falla va antes, aunque lo que no se decidió sea crítico", () => {
    box({ suite: suite({ tests: [unknown, failed] }) });
    expect(screen.getByText("Falla «Reserva una cita»")).toBeInTheDocument();
  });
});

describe("quién paga, en la tarjeta (68.7)", () => {
  const onTheBag = (summary: Partial<ReturnType<typeof suite>["summary"]>) => suite({ next_full_pass: "client_bag", summary: { ...suite().summary, ...summary } });

  it("lo que no pasa se repite primero, y volver a ejecutarlas todas se dice aparte", async () => {
    const ask = vi.fn();
    box({ suite: onTheBag({ total: 8, not_applicable: 0, passed: 6, failed: 2, stale: 0 }), ask });
    await userEvent.click(screen.getByRole("button", { name: "Repetir las que no pasan" }));
    expect(ask).toHaveBeenCalledWith("failed");
    await userEvent.click(screen.getByRole("button", { name: "Repetir todas" }));
    expect(ask).toHaveBeenCalledWith("all");
    expect(screen.getByText(/sale de la bolsa del cliente/)).toBeVisible();
  });

  it("con parte desactualizada y todo en verde, se ofrece esa parte", async () => {
    const ask = vi.fn();
    box({ suite: onTheBag({ total: 8, not_applicable: 0, passed: 8, failed: 0, stale: 3 }), ask });
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar las desactualizadas" }));
    expect(ask).toHaveBeenCalledWith("affected");
  });

  it("con todas desactualizadas no hay atajo: eso es una pasada completa", () => {
    box({ suite: onTheBag({ total: 8, not_applicable: 0, passed: 8, failed: 0, stale: 8 }) });
    expect(screen.queryByRole("button", { name: "Ejecutar las desactualizadas" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Repetir todas" })).toBeVisible();
  });

  it("mientras se estima o arranca, los botones no se pueden volver a pulsar", () => {
    box({ suite: onTheBag({ total: 8, not_applicable: 0, passed: 6, failed: 2, stale: 0 }), pending: true });
    expect(screen.getByRole("button", { name: "Repetir las que no pasan" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Repetir todas" })).toBeDisabled();
  });
});
