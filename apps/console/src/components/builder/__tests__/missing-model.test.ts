import { describe, expect, it } from "vitest";

import type { AgentSpec, MissingCapability } from "@/lib/backend/builder-types";
import { suggestedRole } from "@/lib/backend/suggested-agents";

import { connectByIntegration } from "../builder-model";
import { canConnect, missingCapabilities, missingFrom, notOfferedKeys, pointerValue, specProblemText } from "../missing-model";
import { naReason } from "../quality-model";

/**
 * Spec 047, enmienda del 2026-10-30 «Solo lo que tenemos» (T228; requisitos
 * 65.3, 65.4, 65.7 y 65.8; `contracts/console-api.md` §11) — lo que la consola
 * decide sin pintar nada: qué falta y con qué palabras, a qué nunca se le pone
 * «Conectar {X}», qué papel tiene una sugerencia y cómo se lee la razón de
 * una prueba que no aplica.
 */

const item = (over: Partial<MissingCapability>): MissingCapability => ({
  kind: "integration",
  key: "quickbooks",
  label: "quickbooks",
  reason: "integration_unknown",
  source: "skill",
  pointer: null,
  ...over,
});

describe("lo que falta (65.3, 65.4)", () => {
  it("usa la `label` de cada uno, sin repetidos, en el orden en que llega", () => {
    const list = missingCapabilities([
      item({ key: "quickbooks", label: "quickbooks" }),
      item({ kind: "module", key: "reservas", label: "la agenda (Reservas no está activo para este cliente)", reason: "module_off" }),
      item({ key: "quickbooks", label: "quickbooks" }),
      item({ kind: "action", key: "invoice", label: "emitir facturas", reason: "no_tool", source: "text", pointer: "/procedures/0/steps" }),
      item({ kind: "action", key: "invoice", label: "emitir facturas", reason: "no_tool", source: "text", pointer: "/instructions/sections/1/body" }),
    ]);
    expect(list.map((m) => m.label)).toEqual(["quickbooks", "la agenda (Reservas no está activo para este cliente)", "emitir facturas"]);
    // La primera promesa manda: arreglada esa, la siguiente llega en la lectura de después.
    expect(list[2]!.pointer).toBe("/procedures/0/steps");
  });

  it("parcial: sin `label`, se nombra por su clave; sin `label` ni clave, no se inventa nada", () => {
    const list = missingCapabilities([
      item({ key: "mercadopago", label: "" }),
      item({ key: "", label: "  " }),
      { kind: "tool" } as unknown as MissingCapability,
      null as unknown as MissingCapability,
    ]);
    expect(list.map((m) => m.label)).toEqual(["Mercado Pago"]);
  });

  it("lo que no es una lista no rompe nada: es que no falta nada que se sepa", () => {
    expect(missingCapabilities(undefined)).toEqual([]);
    expect(missingCapabilities(null)).toEqual([]);
    expect(missingCapabilities({ kind: "tool" })).toEqual([]);
  });

  it("lo que falta del borrador; si no lo trae, lo que dejó el trabajo que lo escribió", () => {
    const fromJob = [item({ key: "holded", label: "holded" })];
    expect(missingFrom([item({})], fromJob).map((m) => m.key)).toEqual(["quickbooks"]);
    expect(missingFrom([], fromJob)).toEqual([]);
    expect(missingFrom(undefined, fromJob).map((m) => m.key)).toEqual(["holded"]);
    expect(missingFrom(undefined, undefined)).toEqual([]);
  });
});

describe("«Conectar {X}» solo con lo que ofrecemos (65.3)", () => {
  it("Reservas nunca se conecta: es un módulo, no un conector", () => {
    expect(canConnect("reservas")).toBe(false);
    expect(canConnect("stripe")).toBe(true);
  });

  it("ni lo que la API dice que falta como conector o como módulo", () => {
    const off = notOfferedKeys([
      item({ key: "quickbooks" }),
      item({ kind: "module", key: "agenda_pro", reason: "module_off" }),
      item({ kind: "action", key: "invoice", label: "emitir facturas", reason: "no_tool", source: "text" }),
      item({ kind: "tool", key: "foo.bar", reason: "tool_unknown", source: "tool" }),
    ]);
    expect([...off].sort()).toEqual(["agenda_pro", "quickbooks"]);
    expect(canConnect("quickbooks", off)).toBe(false);
  });

  it("las peticiones de conexión se quedan sin las que no se pueden conectar", () => {
    const connect = [
      { integration: "stripe", reason: "Para cobrar con enlace" },
      { integration: "reservas", reason: "Para reservar" },
      { integration: "quickbooks", reason: "Para facturar" },
    ];
    expect([...connectByIntegration(connect, new Set(["quickbooks"])).keys()]).toEqual(["stripe"]);
    expect([...connectByIntegration(connect).keys()]).toEqual(["stripe", "quickbooks"]);
  });
});

describe("los problemas del validador, en palabras (`integration_unknown`)", () => {
  const spec = {
    schema_version: "1",
    mode: "structured",
    identity: { name: "Cobros", description: "Cobra." },
    skills: [{ key: "facturas", enabled: true, integration: "quickbooks" }],
    connection_requests: [{ integration: "reservas", reason: "Para la agenda" }],
    ai_disclosure: { decided: true },
  } as AgentSpec;
  const t = (key: string, vars?: Record<string, string | number>) => `${key}${vars ? ` ${JSON.stringify(vars)}` : ""}`;

  it("lee el valor al que apunta el puntero", () => {
    expect(pointerValue(spec, "/skills/0/integration")).toBe("quickbooks");
    expect(pointerValue(spec, "/connection_requests/0/integration")).toBe("reservas");
    expect(pointerValue(spec, "/skills/9/integration")).toBeUndefined();
    expect(pointerValue(spec, "")).toBeUndefined();
  });

  it("nombra el conector que no tenemos, y sin nombre lo dice igual", () => {
    expect(specProblemText({ pointer: "/skills/0/integration", code: "integration_unknown", message: "x" }, spec, t)).toBe(
      'builder.problem.integration_unknown {"name":"Quickbooks"}',
    );
    expect(specProblemText({ pointer: "/skills/7/integration", code: "integration_unknown", message: "x" }, spec, t)).toBe(
      "builder.problem.integration_unknown.generic",
    );
  });

  it("los demás problemas siguen con su mensaje (o su código si no lo trae)", () => {
    expect(specProblemText({ pointer: "/rules/0", code: "too_long", message: "La regla es demasiado larga." }, spec, t)).toBe("La regla es demasiado larga.");
    expect(specProblemText({ pointer: "/rules/0", code: "too_long", message: "" }, spec, t)).toBe("too_long");
  });
});

describe("las tarjetas «Sugerido» no exigen papel (65.7)", () => {
  it("un papel que la consola no conoce, o ninguno, cuenta como ninguno", () => {
    expect(suggestedRole("billing")).toBe("billing");
    expect(suggestedRole(null)).toBeNull();
    expect(suggestedRole(undefined)).toBeNull();
    expect(suggestedRole("marketing")).toBeNull();
    expect(suggestedRole(42)).toBeNull();
  });
});

describe("la razón de una prueba que no aplica (65.8)", () => {
  it("no repite «No aplica» si la razón ya lo trae", () => {
    expect(naReason("No aplica: este agente no tiene herramienta para reservar citas.")).toBe("este agente no tiene herramienta para reservar citas.");
    expect(naReason("no aplica. No atendemos mascotas")).toBe("No atendemos mascotas");
    expect(naReason("No atendemos mascotas")).toBe("No atendemos mascotas");
  });
});
