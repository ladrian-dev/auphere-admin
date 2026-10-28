import { describe, expect, it } from "vitest";

import type { TestSummary } from "@/lib/backend/agent-quality-types";

import {
  AGENT_ROWS,
  ROW_BLOCKS,
  barState,
  checkOfFinding,
  editableBlocks,
  findingsByCheck,
  inMore,
  rowOfBlock,
  rowOfSection,
  testsState,
} from "../agent-proto-model";
import { AGENT_BLOCKS } from "../builder-model";
import { REVIEW, preview } from "./quality-fixtures";

/**
 * «Configuración» como el prototipo aprobado (spec 047, prototipo
 * `agente.md` §4, §5 y §12): los 9 bloques del AgentSpec en las 5 filas, qué
 * vive en «Más ajustes», en qué punto están las pruebas y qué dice la barra.
 */

function summary(over: Partial<TestSummary> = {}): TestSummary {
  return {
    passed: 0,
    flaky: 0,
    failed: 0,
    unknown: 0,
    not_run: 0,
    not_applicable: 0,
    total: 0,
    stale: 0,
    critical_failed: [],
    rate: null,
    ...over,
  };
}

describe("las cinco filas (§12)", () => {
  it("cada bloque del AgentSpec cae en una sola fila, en el orden del prototipo", () => {
    expect(AGENT_ROWS).toEqual(["does", "speaks", "knows", "can", "handoff"]);
    const all = AGENT_ROWS.flatMap((row) => ROW_BLOCKS[row]);
    expect([...all].sort()).toEqual([...AGENT_BLOCKS].sort());
    expect(ROW_BLOCKS.does).toEqual(["identity", "instructions", "rules"]);
    expect(ROW_BLOCKS.speaks).toEqual(["voice", "ai_disclosure"]);
    expect(ROW_BLOCKS.knows).toEqual(["services"]);
    expect(ROW_BLOCKS.can).toEqual(["skills", "procedures"]);
    expect(ROW_BLOCKS.handoff).toEqual(["escalation"]);
  });

  it("dice la fila de un bloque y de un ancla", () => {
    expect(rowOfBlock("rules")).toBe("does");
    expect(rowOfBlock("ai_disclosure")).toBe("speaks");
    expect(rowOfBlock("procedures")).toBe("can");
    expect(rowOfBlock("tests")).toBeNull();
    expect(rowOfSection("bloque-escalation")).toBe("handoff");
    expect(rowOfSection("agente-conocimiento")).toBe("knows");
    expect(rowOfSection("agente-pruebas")).toBeNull();
  });

  it("solo abre editores que existen", () => {
    expect(editableBlocks("does")).toEqual(["identity", "instructions", "rules"]);
    expect(editableBlocks("can")).toEqual(["procedures"]);
    expect(editableBlocks("knows")).toEqual([]);
  });

  it("«Más ajustes» guarda lo que no está en el prototipo", () => {
    for (const id of ["agente-recepcion", "agente-pruebas", "agente-revision", "agente-historial", "agente-avanzado", "agente-calidad", "agente-copiloto", "agente-propuestas"]) {
      expect(inMore(id), id).toBe(true);
    }
    expect(inMore("agente-conocimiento")).toBe(false);
    expect(inMore("bloque-rules")).toBe(false);
    expect(inMore(null)).toBe(false);
  });
});

describe("en qué punto están las pruebas (§5.1)", () => {
  it("sin pruebas que cuenten, ninguna", () => {
    expect(testsState(summary())).toEqual({ kind: "none" });
    expect(testsState(summary({ total: 2, not_applicable: 2 }))).toEqual({ kind: "none" });
  });

  it("con alguna sin ejecutar o desactualizada, no han terminado", () => {
    expect(testsState(summary({ total: 6, not_applicable: 1, passed: 1, failed: 1, flaky: 1, unknown: 1, not_run: 1, stale: 1 }))).toEqual({
      kind: "pending",
      pending: 2,
      counted: 5,
    })
  });

  it("todas ejecutadas: pasan todas, o cuántas no", () => {
    expect(testsState(summary({ total: 20, passed: 20 }))).toEqual({ kind: "passing", passed: 20, counted: 20 });
    expect(testsState(summary({ total: 20, passed: 19, failed: 1 }))).toEqual({ kind: "failing", failing: 1, passed: 19, counted: 20 });
    expect(testsState(summary({ total: 20, passed: 17, flaky: 2, unknown: 1 }))).toEqual({ kind: "failing", failing: 3, passed: 17, counted: 20 });
  });
});

describe("la revisión en la tarjeta de pruebas", () => {
  it("cada hallazgo va con su comprobación, por su código", () => {
    expect(checkOfFinding("skill_without_integration")).toBe("skills_integrations");
    expect(checkOfFinding("service_without_price")).toBe("services");
    expect(checkOfFinding("bookable_without_duration")).toBe("services");
    expect(checkOfFinding("contradicts_business")).toBe("contradictions");
    expect(checkOfFinding("unknown_tool")).toBe("tools_exist");
    expect(checkOfFinding("ai_disclosure_undecided")).toBe("ai_disclosure");
    expect(checkOfFinding("algo_nuevo")).toBeNull();
    const by = findingsByCheck(REVIEW);
    expect(by.get("skills_integrations")?.map((f) => f.code)).toEqual(["skill_without_integration"]);
    expect(by.get("services")?.map((f) => f.code)).toEqual(["service_without_price"]);
    expect(by.get("contradictions")?.map((f) => f.code)).toEqual(["contradicts_hours"]);
  });
});

describe("la barra flotante (§4.5)", () => {
  const passing = summary({ total: 5, passed: 5 });
  const failing = summary({ total: 5, passed: 4, failed: 1 });
  const pending = summary({ total: 5, passed: 2, not_run: 3 });

  it("sin permiso, solo lectura", () => {
    expect(barState({ canWrite: false, preview: preview(), tests: { summary: passing, running: false, canRun: true } })).toEqual({ kind: "readonly" });
  });

  it("pruebas en marcha", () => {
    expect(barState({ canWrite: true, preview: preview(), tests: { summary: pending, running: true, canRun: true } })).toEqual({ kind: "running" });
  });

  it("terminadas con fallos: lo dice y deja guardar igualmente si hay borrador", () => {
    expect(barState({ canWrite: true, preview: preview(), tests: { summary: failing, running: false, canRun: true } })).toEqual({
      kind: "failing",
      failing: 1,
      total: 5,
      save: true,
    });
    expect(barState({ canWrite: true, preview: preview({ has_draft: false }), tests: { summary: failing, running: false, canRun: true } })).toMatchObject({ save: false });
  });

  it("todas pasan: guardar lo que diga la API, o conectar un canal si ya está guardado y no tiene", () => {
    expect(barState({ canWrite: true, preview: preview({ action: "save_and_connect" }), tests: { summary: passing, running: false, canRun: true } })).toEqual({
      kind: "passing",
      passed: 5,
      total: 5,
      saved: false,
      next: "save",
    });
    expect(barState({ canWrite: true, preview: preview({ has_draft: false, has_channels: false }), tests: { summary: passing, running: false, canRun: true } })).toEqual({
      kind: "passing",
      passed: 5,
      total: 5,
      saved: true,
      next: "connect",
    });
    expect(barState({ canWrite: true, preview: preview({ has_draft: false, has_channels: true }), tests: { summary: passing, running: false, canRun: true } })).toMatchObject({
      saved: true,
      next: null,
    });
  });

  it("sin ejecutar: «Borrador completo» y «Ejecutar pruebas»", () => {
    expect(barState({ canWrite: true, preview: preview(), tests: { summary: pending, running: false, canRun: true } })).toEqual({ kind: "pending", draft: true });
  });

  it("sin datos de pruebas o sin poder ejecutarlas, la barra de siempre", () => {
    expect(barState({ canWrite: true, preview: preview(), tests: null })).toEqual({ kind: "plain" });
    expect(barState({ canWrite: true, preview: preview(), tests: { summary: pending, running: false, canRun: false } })).toEqual({ kind: "plain" });
    expect(barState({ canWrite: true, preview: preview(), tests: { summary: summary(), running: false, canRun: true } })).toEqual({ kind: "plain" });
  });
});
