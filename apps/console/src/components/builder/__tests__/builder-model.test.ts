import { describe, expect, it } from "vitest";

import type { AgentSpec, BuilderBlock, DraftJob } from "@/lib/backend/builder-types";

import {
  BOOKING_WORDS,
  POLL_FIRST_MS,
  agendaSuggested,
  blocksOfOps,
  sectionForTab,
  POLL_MAX_MS,
  arrivedBlocks,
  blockOfPointer,
  describeProblems,
  draftSteps,
  groupTemplates,
  integrationName,
  nextDelay,
  parseLanguages,
  problemsOf,
  procedureId,
  tabOfSection,
  toggleLanguage,
  withBlock,
  withExample,
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
    expect(integrationName("googlecalendar")).toBe("Google Calendar");
    expect(integrationName("mi_crm")).toBe("Mi crm");
  });
});

/**
 * El prototipo aprobado parte la pantalla del agente en cuatro pestañas. Un
 * aviso (`?tab=`) o un enlace (`#agente-pruebas`) sigue llevando a su sección:
 * primero se abre la pestaña que la tiene.
 */
describe("tabOfSection", () => {
  it("cada sección, en su pestaña", () => {
    expect(tabOfSection("agente-rendimiento")).toBe("perf");
    expect(tabOfSection("agente-mejoras")).toBe("perf");
    expect(tabOfSection("agente-canales")).toBe("channels");
    expect(tabOfSection("agente-conectores")).toBe("connectors");
    for (const id of ["agente-borrador", "agente-pruebas", "agente-revision", "agente-historial", "agente-avanzado", "agente-calidad", "agente-recepcion", "agente-conocimiento", "agente-copiloto", "bloque-voice"]) {
      expect(tabOfSection(id)).toBe("build");
    }
  });

  it("lo que no es de la pantalla del agente no abre ninguna", () => {
    expect(tabOfSection(null)).toBeNull();
    expect(tabOfSection("")).toBeNull();
    expect(tabOfSection("canal-escalado")).toBeNull();
  });
});

/**
 * «Nuevo agente» como el prototipo (§3.2): los cuatro pasos dicen lo que el
 * trabajo ya contó, nada más. Un paso está hecho cuando el trabajo lo dejó
 * atrás (pasó a escribir, llegaron las pruebas, llegaron las preguntas, terminó);
 * el primero sin hacer está en curso y los demás esperan. Lo que la consulta no
 * llegó a ver se marca de una vez al terminar.
 */
describe("draftSteps", () => {
  const at = (over: Partial<DraftJob>): DraftJob => ({ ...job([]), ...over });

  it("sin trabajo o en cola, el primero está en curso", () => {
    expect(draftSteps(null)).toEqual(["active", "wait", "wait", "wait"]);
    expect(draftSteps(at({ status: "queued", progress: null }))).toEqual(["active", "wait", "wait", "wait"]);
    expect(draftSteps(at({ progress: { step: "reading", blocks: [] } }))).toEqual(["active", "wait", "wait", "wait"]);
  });

  it("escribiendo, la ficha ya está leída; las pruebas y las preguntas cierran los suyos", () => {
    expect(draftSteps(at({ progress: { step: "writing", blocks: [] } }))).toEqual(["done", "active", "wait", "wait"]);
    expect(draftSteps(at({ progress: { step: "writing", blocks: [{ key: "identity" }, { key: "voice" }] } }))).toEqual(["done", "active", "wait", "wait"]);
    expect(draftSteps(at({ progress: { step: "writing", blocks: [{ key: "identity" }, { key: "tests", count: 8 }] } }))).toEqual([
      "done",
      "done",
      "active",
      "wait",
    ]);
    expect(draftSteps(at({ progress: { step: "writing", blocks: [{ key: "tests", count: 8 }, { key: "questions", count: 2 }] } }))).toEqual([
      "done",
      "done",
      "done",
      "active",
    ]);
  });

  it("terminado, todos hechos aunque la consulta no viera los pasos de en medio", () => {
    expect(draftSteps(at({ status: "done", progress: { step: "reading", blocks: [] } }))).toEqual(["done", "done", "done", "done"]);
  });
});

/** «Idiomas» se marcan: el primero que se marca es el principal; como mucho cinco. */
describe("toggleLanguage", () => {
  it("añade al final, quita sin mover el resto y no pasa de cinco", () => {
    expect(toggleLanguage([], "es")).toEqual(["es"]);
    expect(toggleLanguage(["es"], "en")).toEqual(["es", "en"]);
    expect(toggleLanguage(["es", "en", "pt"], "es")).toEqual(["en", "pt"]);
    expect(toggleLanguage(["es", "en", "pt", "fr", "it"], "de")).toEqual(["es", "en", "pt", "fr", "it"]);
  });
});

describe("withExample (spec 055)", () => {
  it("fills an empty description", () => {
    expect(withExample("  ", "Ejemplo.", 100)).toEqual({ kind: "ok", text: "Ejemplo." });
  });

  it("adds it in its own paragraph, leaving what was written as it was", () => {
    expect(withExample("Lo mío.\n", "Ejemplo.", 100)).toEqual({ kind: "ok", text: "Lo mío.\n\nEjemplo." });
  });

  it("does not repeat it", () => {
    expect(withExample("Lo mío.\n\nEjemplo.", "Ejemplo.", 100)).toEqual({ kind: "already" });
  });

  it("never cuts: without room it says so", () => {
    expect(withExample("x".repeat(95), "Ejemplo.", 100)).toEqual({ kind: "no_room" });
    expect(withExample("", "y".repeat(101), 100)).toEqual({ kind: "no_room" });
  });
});

/**
 * Spec 057 (requisito 1.2) — «Gestiona citas» se enciende solo, mientras nadie lo
 * toque, si la descripción pide citas, reservas o turnos (la misma expresión que
 * `agent_draft._BOOKING` de la API) o la plantilla elegida da citas.
 */
describe("agendaSuggested (spec 057)", () => {
  it("las palabras de la API, sin mayúsculas que valgan, y solo palabras enteras", () => {
    for (const text of ["Da citas por WhatsApp", "Gestiona la CITA de cada cliente", "Reserva mesas", "Toma reservaciones", "Agenda las visitas", "Para agendar", "Da un turno", "Da turnos de noche"]) {
      expect(BOOKING_WORDS.test(text), text).toBe(true);
    }
    for (const text of ["Cobra las facturas pendientes", "Recitas poemas", "Nocturnos y diurnos", "Responde dudas de envíos"]) {
      expect(BOOKING_WORDS.test(text), text).toBe(false);
    }
  });

  it("por la descripción o por la plantilla, y dice por qué", () => {
    expect(agendaSuggested("Atiende las citas del salón", null)).toBe("description");
    expect(agendaSuggested("Cobra las facturas pendientes", { books: true })).toBe("template");
    expect(agendaSuggested("Cobra las facturas pendientes", { books: false })).toBeNull();
    expect(agendaSuggested("Cobra las facturas pendientes", null)).toBeNull();
  });
});

describe("la fila de la agenda en Conectores (spec 057)", () => {
  it("`#agenda` y `?tab=agenda` llevan a la pestaña Conectores", () => {
    expect(tabOfSection("agenda")).toBe("connectors");
    expect(sectionForTab("agenda")).toBe("agenda");
  });
});

/** Spec 057 (3.3): la propuesta por bloque, con lo de antes y lo de después. */
describe("blocksOfOps (spec 057)", () => {
  it("agrupa por bloque en el orden en que llegan; un puntero sin bloque va aparte", () => {
    const groups = blocksOfOps([
      { op: "replace", path: "/procedures/0/steps", value: "Busca hueco", before: "Pasa al equipo" },
      { op: "remove", path: "/rules/1", before: "El equipo confirma" },
      { op: "add", path: "/procedures/-", value: { id: "mover" }, before: null },
      { op: "replace", path: "/policies/x", value: "y" },
    ]);
    expect(groups.map((g) => g.block)).toEqual(["procedures", "rules", null]);
    expect(groups[0]!.ops).toHaveLength(2);
    expect(groups[2]!.ops[0]!.path).toBe("/policies/x");
  });
});
