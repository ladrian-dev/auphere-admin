/**
 * Requisito 15.3 — el ambiente del agente no alcanza la sesión de la persona.
 *
 * **Es la condición de esta fase, y va primero.** §VI prohíbe que un agente
 * navegue la consola de Auphere *precisamente porque* eso mete una sesión
 * autenticada dentro de su ambiente. La cáscara tiene esa sesión en la misma
 * máquina donde el agente ejecuta comandos, así que lo único que separa una cosa
 * de la otra es esto. Si no se sostiene, envolver la consola viola §VI y hay que
 * replantear la cáscara antes de construirla.
 *
 * La separación no puede ser «el agente no mirará ahí»: tiene que ser que no haya
 * dónde mirar.
 */
import { describe, expect, it } from "vitest";

import {
  AGENT_PARTITION,
  HUMAN_PARTITION,
  agentProcessEnv,
  assertPartitionsAreSeparate,
  sessionCookieNames,
} from "../src/session-isolation.js";

describe("las dos particiones no se tocan (15.3)", () => {
  it("la del agente y la de la persona son distintas", () => {
    expect(AGENT_PARTITION).not.toBe(HUMAN_PARTITION);
    expect(() => assertPartitionsAreSeparate()).not.toThrow();
  });

  it("la del agente no es persistente: no hay dónde quedarse una sesión", () => {
    expect(AGENT_PARTITION.startsWith("persist:")).toBe(false);
    expect(HUMAN_PARTITION.startsWith("persist:")).toBe(true);
  });

  it("si alguien las igualara, esto se entera", () => {
    expect(() => assertPartitionsAreSeparate("persist:x", "persist:x")).toThrow();
  });
});

describe("las cookies de la persona no viajan al agente", () => {
  it("ninguna cookie de sesión aparece en la partición del agente", () => {
    const humanCookies = sessionCookieNames(HUMAN_PARTITION);
    const agentCookies = sessionCookieNames(AGENT_PARTITION);
    expect(agentCookies).toHaveLength(0);
    expect(humanCookies.every((c) => !agentCookies.includes(c))).toBe(true);
  });
});

describe("el entorno del proceso del agente (15.3 y 7.4)", () => {
  it("no lleva el token de la consola aunque esté en el entorno de la app", () => {
    const env = agentProcessEnv({
      PATH: "/usr/bin",
      HOME: "/Users/partner",
      AUPHERE_CONSOLE_SESSION: "sesion-de-luis",
      NEXUS_ADMIN_TOKEN: "no-deberia-existir-siquiera",
    });
    expect(env).not.toHaveProperty("AUPHERE_CONSOLE_SESSION");
    expect(env).not.toHaveProperty("NEXUS_ADMIN_TOKEN");
  });

  it("se construye por lista blanca: lo desconocido no pasa", () => {
    const env = agentProcessEnv({ PATH: "/usr/bin", VARIABLE_NUEVA_DE_MAÑANA: "x" });
    expect(env).not.toHaveProperty("VARIABLE_NUEVA_DE_MAÑANA");
    expect(env.PATH).toBe("/usr/bin");
  });

  it("lo que el proceso necesita para arrancar sí pasa", () => {
    const env = agentProcessEnv({ PATH: "/usr/bin", HOME: "/Users/partner", LANG: "es_ES.UTF-8" });
    expect(Object.keys(env).sort()).toEqual(["HOME", "LANG", "PATH"]);
  });
});
