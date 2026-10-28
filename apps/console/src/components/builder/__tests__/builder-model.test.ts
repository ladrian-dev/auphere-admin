import { describe, expect, it } from "vitest";

import type { AgentSpec, BuilderBlock, DraftJob } from "@/lib/backend/builder-types";

import {
  POLL_FIRST_MS,
  POLL_MAX_MS,
  arrivedBlocks,
  blockOfPointer,
  describeProblems,
  groupTemplates,
  integrationName,
  nextDelay,
  parseLanguages,
  problemsOf,
  procedureId,
  withBlock,
} from "../builder-model";

/**
 * Spec 047 (historia 7, T081) — lo que el constructor decide sin pintar nada:
 * la espera creciente, el orden de los bloques, los límites de la descripción y
 * cómo se escribe un bloque dentro del AgentSpec.
 */

const job = (blocks: { key: string }[]): DraftJob => ({
  job_id: "j",
  kind: "agent_draft",
  status: "running",
  agent_id: null,
  progress: { step: "writing", blocks: blocks as BuilderBlock[] },
  result: null,
  error_code: null,
  created_at: "2026-10-27T10:00:00Z",
  finished_at: null,
});

describe("la espera al consultar el trabajo", () => {
  it("crece 1, 2, 4… hasta 10 s mientras nada cambia", () => {
    const seen: number[] = [POLL_FIRST_MS];
    for (let i = 0; i < 6; i += 1) seen.push(nextDelay(seen[seen.length - 1]!, false));
    expect(seen).toEqual([1000, 2000, 4000, 8000, 10_000, 10_000, 10_000]);
    expect(Math.max(...seen)).toBe(POLL_MAX_MS);
  });

  it("vuelve a 1 s cuando llega un bloque nuevo", () => {
    expect(nextDelay(8000, true)).toBe(1000);
  });
});

describe("los bloques que llegaron", () => {
  it("salen en el orden del borrador, uno por clave, y lo desconocido se calla", () => {
    const blocks = arrivedBlocks(job([{ key: "voice" }, { key: "identity" }, { key: "nope" }, { key: "voice" }, { key: "tests" }]));
    expect(blocks.map((b) => b.key)).toEqual(["identity", "voice", "tests"]);
    expect(arrivedBlocks(null)).toEqual([]);
  });
});

describe("los límites de «Nuevo agente» (17.1)", () => {
  it("nombre de 1 a 40 y descripción de 20 a 1.024", () => {
    expect(describeProblems("Recepción", "Atiende las citas por WhatsApp.")).toEqual({ name: false, description: false });
    expect(describeProblems("   ", "Atiende las citas por WhatsApp.").name).toBe(true);
    expect(describeProblems("x".repeat(41), "Atiende las citas por WhatsApp.").name).toBe(true);
    expect(describeProblems("Recepción", "Muy corta").description).toBe(true);
    expect(describeProblems("Recepción", "x".repeat(1025)).description).toBe(true);
    expect(describeProblems("Recepción", "x".repeat(1024)).description).toBe(false);
  });
});

describe("piezas del AgentSpec", () => {
  it("los idiomas son códigos BCP 47, de 1 a 5", () => {
    expect(parseLanguages("es, pt-BR")).toEqual(["es", "pt-BR"]);
    expect(parseLanguages("")).toEqual([]);
    expect(parseLanguages("español")).toBeNull();
    expect(parseLanguages("es, en, fr, de, it, pt")).toBeNull();
  });

  it("un procedimiento nuevo tiene un id válido y único", () => {
    expect(procedureId("Pedir factura", new Set())).toBe("pedir_factura");
    expect(procedureId("Pedir factura", new Set(["pedir_factura"]))).toBe("pedir_factura_2");
    expect(procedureId("¡¡!!", new Set())).toBe("procedimiento");
    expect(procedureId("Reservar una cita", new Set())).toMatch(/^[a-z0-9_]{1,40}$/);
  });

  it("escribir un bloque deja el resto del documento tal cual", () => {
    const spec = {
      schema_version: "1",
      mode: "structured",
      identity: { name: "Recepción", description: "Atiende las citas de la barbería." },
      rules: ["No ofrezcas descuentos"],
      ai_disclosure: { decided: false },
      model_policy: { kind: "profile", profile: "auto" },
    } as AgentSpec;
    const next = withBlock(spec, "rules", ["No des precios por teléfono"]);
    expect(next.rules).toEqual(["No des precios por teléfono"]);
    expect(next.model_policy).toEqual(spec.model_policy);
    expect(spec.rules).toEqual(["No ofrezcas descuentos"]);
    expect("rules" in withBlock(spec, "rules", undefined)).toBe(false);
  });

  it("los problemas y las operaciones se reparten por bloque", () => {
    const problems = [
      { pointer: "/rules/2", code: "too_long", message: "Demasiado larga" },
      { pointer: "/identity/name", code: "required", message: "Falta" },
    ];
    expect(problemsOf(problems, "rules").map((p) => p.code)).toEqual(["too_long"]);
    expect(blockOfPointer("/rules/-")).toBe("rules");
    expect(blockOfPointer("/connection_requests/0")).toBe("skills");
    expect(blockOfPointer("/model_policy")).toBeNull();
    // El arreglo de «Falta decidir si el agente dice que es una IA» abre su bloque.
    expect(blockOfPointer("/ai_disclosure")).toBe("ai_disclosure");
    expect(blockOfPointer("/ai_disclosure/mode")).toBe("ai_disclosure");
  });

  it("las plantillas se agrupan en el orden en que llegan, la del partner primero", () => {
    const groups = groupTemplates([
      { id: "a", group: "Belleza" },
      { id: "b", group: "Salud" },
      { id: "c", group: "Belleza" },
    ]);
    expect(groups.map((g) => [g.group, g.items.map((i) => i.id)])).toEqual([
      ["Belleza", ["a", "c"]],
      ["Salud", ["b"]],
    ]);
  });

  it("los conectores se llaman por su marca", () => {
    expect(integrationName("agendapro")).toBe("AgendaPro");
    expect(integrationName("mi_crm")).toBe("Mi crm");
  });
});
