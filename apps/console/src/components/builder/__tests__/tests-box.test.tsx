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
    expect(within(container).getByRole("button", { name: "Ejecutar la prueba" })).toBeVisible();
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

describe("sin ejecutar, una sola vez y con lo que cuestan (spec 073, 3b.3)", () => {
  const stale = suite({ summary: { ...suite().summary, total: 8, not_applicable: 0, passed: 0, failed: 0, flaky: 0, unknown: 0, not_run: 0, stale: 8, model_failed: 0 } });

  it("dice cuántas, las ejecuta todas y avisa de lo que costarían", () => {
    box({ suite: stale, cost: { charge: { amount_micros: 40_000, currency: "USD" }, unknown: false } });
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Pruebas · 8 sin ejecutar");
    expect(screen.getByRole("button", { name: "Ejecutar las 8 pruebas" })).toBeVisible();
    expect(screen.getByText("Costarían unos 0,40 USD.")).toBeVisible();
  });

  it("sin precio no inventa una cifra", () => {
    box({ suite: stale, cost: { charge: null, unknown: true } });
    expect(screen.getByText("No se puede calcular el coste.")).toBeVisible();
    expect(screen.queryByText(/Costarían/)).toBeNull();
  });
});

/**
 * Bug `la-revision-ve-lo-que-no-hay`: una promesa sin herramienta ya la enseña, con su
 * «Quitar la promesa», «No tenemos herramienta para» encima del borrador. La revisión de
 * la tarjeta no la repite una a una: dice cuántas y lleva allí. Lo demás sigue igual.
 */
describe("la revisión de la tarjeta no repite lo que falta", () => {
  const promise = (label: string, i: number) => ({
    code: "promises_without_tool",
    severity: "block" as const,
    message: `Las instrucciones prometen ${label} y el agente no tiene ninguna herramienta que lo haga.`,
    pointer: `/rules/${i}`,
    fix: { kind: "edit" as const, pointer: `/rules/${i}` },
  });
  const review = {
    version_number: 3,
    findings: [
      promise("cobrar con tarjeta o con enlace de pago", 0),
      promise("enviar una factura", 1),
      {
        code: "forbids_agenda",
        severity: "warn" as const,
        message: "El agente tiene la agenda, pero este texto dice que no reserva: «No reserves».",
        pointer: "/rules/2",
        fix: { kind: "edit" as const, pointer: "/rules/2" },
      },
    ],
    checks: [
      { check: "skills_integrations", ok: true, findings: 0 },
      { check: "contradictions", ok: true, findings: 0 },
      { check: "services", ok: true, findings: 0 },
      { check: "promises", ok: false, findings: 3 },
    ],
    blocking: 2,
  };
  const source = { review, state: "ready" as const, applying: null, load: vi.fn(), apply: vi.fn() };

  it("dice cuántas promesas, enlaza a lo que falta y deja el resto", async () => {
    const tests: Tests = { suite: suite(), running: null, pending: false, error: null, canRun: true, run: vi.fn(), ask: vi.fn(), confirm: null, reload: vi.fn() };
    const { container } = render(
      <LocaleProvider locale="es">
        <TestsBox refId={REF} tests={tests} review={source} canWrite onFix={vi.fn()} onEdit={vi.fn()} onAll={vi.fn()} />
      </LocaleProvider>,
    );
    const checks = within(screen.getByRole("list", { name: "Revisión automática" }));
    expect(checks.queryByText(/cobrar con tarjeta/)).toBeNull();
    expect(checks.queryByText(/enviar una factura/)).toBeNull();
    expect(checks.getByText(/Su texto promete 2 cosas que ninguna herramienta hace\./)).toBeVisible();
    expect(checks.getByRole("link", { name: "Ver cuáles" })).toHaveAttribute("href", "#agente-faltan");
    // Lo que «No tenemos herramienta para» no enseña sigue aquí, con su texto.
    expect(checks.getByText(/«No reserves»/)).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });
});
