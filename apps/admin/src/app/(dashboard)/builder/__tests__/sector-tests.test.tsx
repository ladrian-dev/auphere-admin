import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SectorCatalog, SectorTest } from "@/lib/backend-builder";

const h = vi.hoisted(() => ({ publish: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  publishSectorTestsAction: (...a: unknown[]) => h.publish(...a),
  calibrateJudgeAction: vi.fn(),
  runEvalAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { SectorCatalogView } = await import("../sector-tests/sector-catalog");
const { blankTest, formFromTest, formsFromCatalog, testsFromForms, testsWithErrors } = await import(
  "../sector-tests/sector-tests"
);

function test(i: number, o: Partial<SectorTest> = {}): SectorTest {
  return {
    key: `t${i}`,
    name: `Prueba ${i}`,
    persona: "Cliente habitual",
    first_message: `Hola ${i}`,
    plan: "Acepta lo primero que le ofrezcan.",
    expected_state: i === 0 ? { booking: { created: true } } : {},
    criteria: [{ key: "ok", text: "Responde con lo de la ficha." }],
    critical: i === 0,
    ...o,
  };
}

const TWELVE = Array.from({ length: 12 }, (_, i) => test(i));
const BARBER: SectorCatalog = {
  sector: "barberia_peluqueria",
  name: "Barbería y peluquería",
  version: 1,
  published_at: "2026-10-27T10:00:00Z",
  published_by: "auphere:spec-047",
  tests: TWELVE,
};
const CLINIC: SectorCatalog = {
  sector: "clinica",
  name: "Clínica dental y estética",
  version: null,
  published_at: null,
  published_by: null,
  tests: [],
};
const OPERATOR = "11111111-2222-3333-4444-555555555555";

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T090, 21.2, 54.10): 12 tests per sector, each one complete. */
describe("the sector tests as the editor sees them", () => {
  it("goes to the form and back without changing a test", () => {
    const checked = testsFromForms(TWELVE.map(formFromTest));
    expect(checked).toEqual({ ok: true, tests: TWELVE });
  });

  it("starts an empty sector with 12 empty tests", () => {
    expect(formsFromCatalog([])).toHaveLength(12);
  });

  it("asks for exactly 12, with unique keys", () => {
    const eleven = testsFromForms(TWELVE.slice(0, 11).map(formFromTest));
    expect(eleven.ok).toBe(false);
    if (!eleven.ok) expect(eleven.errors.count).toMatch(/exactamente 12/);

    const twin = testsFromForms([...TWELVE.slice(0, 11), test(0)].map(formFromTest));
    expect(twin.ok).toBe(false);
    if (!twin.ok) expect(twin.errors["11.key"]).toMatch(/ya la usa la prueba 1/);
  });

  it("checks each field like the API does", () => {
    const forms = TWELVE.map(formFromTest);
    forms[1] = { ...forms[1]!, key: "Con Mayúsculas" };
    forms[2] = { ...forms[2]!, name: "  " };
    forms[3] = { ...forms[3]!, first_message: "" };
    forms[4] = { ...forms[4]!, expected_state: "[1, 2]" };
    forms[5] = { ...forms[5]!, expected_state: "{no es json" };
    forms[6] = { ...forms[6]!, criteria: [] };
    forms[7] = { ...forms[7]!, criteria: Array.from({ length: 7 }, (_, j) => ({ uid: `c${j}`, key: `c${j}`, text: "x" })) };
    forms[8] = {
      ...forms[8]!,
      criteria: [
        { uid: "a", key: "dup", text: "uno" },
        { uid: "b", key: "dup", text: "" },
      ],
    };
    const checked = testsFromForms(forms);
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(checked.errors["1.key"]).toMatch(/Minúsculas/);
    expect(checked.errors["2.name"]).toBe("Hace falta el nombre.");
    expect(checked.errors["3.first_message"]).toBe("Hace falta el primer mensaje.");
    expect(checked.errors["4.expected_state"]).toMatch(/objeto JSON/);
    expect(checked.errors["5.expected_state"]).toMatch(/objeto JSON/);
    expect(checked.errors["6.criteria"]).toMatch(/Entre 1 y 6/);
    expect(checked.errors["7.criteria"]).toMatch(/Entre 1 y 6/);
    expect(checked.errors["8.criteria.1.key"]).toMatch(/Repetida/);
    expect(checked.errors["8.criteria.1.text"]).toBe("Hace falta el criterio.");
    expect([...testsWithErrors(checked.errors)].sort()).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("an empty test is not valid", () => {
    const checked = testsFromForms([...TWELVE.slice(0, 11).map(formFromTest), blankTest()]);
    expect(checked.ok).toBe(false);
    if (!checked.ok) expect(Object.keys(checked.errors)).toEqual(expect.arrayContaining(["11.key", "11.name", "11.first_message"]));
  });
});

describe("the sector catalog screen", () => {
  it("shows the version in force, who published it and its 12 tests", () => {
    render(<SectorCatalogView sectors={[BARBER, CLINIC]} operatorId={OPERATOR} />);
    expect(screen.getByRole("button", { name: "Barbería y peluquería" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/En vigor la versión 1 · 12 pruebas · publicada por Semilla \(spec-047\)/)).toBeTruthy();
    const list = screen.getByRole("list", { name: "Pruebas de Barbería y peluquería" });
    expect(list.children).toHaveLength(12);
    expect(within(list).getAllByText("Crítica")).toHaveLength(1);
  });

  it("offers to write version 1 of a sector without one", async () => {
    render(<SectorCatalogView sectors={[BARBER, CLINIC]} operatorId={OPERATOR} />);
    await userEvent.click(screen.getByRole("button", { name: "Clínica dental y estética" }));
    expect(screen.getByText("Clínica dental y estética no tiene pruebas publicadas")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Escribir la versión 1" }));
    expect(screen.getByText("12 de 12 pruebas")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Publicar la versión 1" })).toBeTruthy();
  });

  it("publishes a new version with the 12 tests, edited", async () => {
    h.publish.mockResolvedValue({ ok: true, data: { ...BARBER, version: 2 } });
    render(<SectorCatalogView sectors={[BARBER, CLINIC]} operatorId={OPERATOR} />);
    await userEvent.click(screen.getByRole("button", { name: "Editar y publicar versión nueva" }));
    // While editing, the sector does not change.
    expect((screen.getByRole("button", { name: "Clínica dental y estética" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /Prueba 0/ }));
    const first = screen.getByRole("group", { name: "Prueba 1" });
    const name = within(first).getByRole("textbox", { name: /Nombre/ });
    await userEvent.clear(name);
    await userEvent.type(name, "Pide cita para pasado mañana");
    await userEvent.click(screen.getByRole("button", { name: "Publicar la versión 2" }));
    expect(h.publish).toHaveBeenCalledTimes(1);
    const [sector, tests] = h.publish.mock.calls[0] as [string, SectorTest[]];
    expect(sector).toBe("barberia_peluqueria");
    expect(tests).toHaveLength(12);
    expect(tests[0]).toEqual({ ...TWELVE[0], name: "Pide cita para pasado mañana" });
    expect(tests.slice(1)).toEqual(TWELVE.slice(1));
    expect(h.success).toHaveBeenCalledWith("Barbería y peluquería: versión 2 publicada");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("does not publish 11 tests, and opens the test that has something to fix", async () => {
    render(<SectorCatalogView sectors={[BARBER]} operatorId={OPERATOR} />);
    await userEvent.click(screen.getByRole("button", { name: "Editar y publicar versión nueva" }));
    await userEvent.click(screen.getByRole("button", { name: "Quitar la prueba 12" }));
    expect(screen.getByText("11 de 12 pruebas")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Publicar la versión 2" }));
    expect(h.publish).not.toHaveBeenCalled();
    expect(screen.getByText(/ahora hay 11/)).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Añadir prueba" }));
    await userEvent.click(screen.getByRole("button", { name: "Publicar la versión 2" }));
    expect(h.publish).not.toHaveBeenCalled();
    const added = screen.getByRole("group", { name: "Prueba 12" });
    // The test's key and its first criterion's key.
    expect(within(added).getAllByText("Hace falta la clave.")).toHaveLength(2);
    expect(within(added).getByRole("textbox", { name: /^Clave(?! del)/ }).getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText(/en la prueba 12\./)).toBeTruthy();
  });

  it("says the API's refusal by its code", async () => {
    h.publish.mockResolvedValue({
      ok: false,
      code: "duplicate_key",
      error: "Dos pruebas tienen la misma clave.",
    });
    render(<SectorCatalogView sectors={[BARBER]} operatorId={OPERATOR} />);
    await userEvent.click(screen.getByRole("button", { name: "Editar y publicar versión nueva" }));
    await userEvent.click(screen.getByRole("button", { name: "Publicar la versión 2" }));
    expect(screen.getByRole("alert").textContent).toBe("Dos pruebas tienen la misma clave.");
    expect(h.refresh).not.toHaveBeenCalled();
  });
});
