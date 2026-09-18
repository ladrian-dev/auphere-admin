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
  APP_PARTITION,
  HUMAN_PARTITION,
  agentProcessEnv,
  appWebPreferences,
  assertPartitionsAreSeparate,
  consoleWebPreferences,
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

/*
 * Spec 010, T015 — **la partición de la barra se retira con la barra.**
 *
 * Eran cuatro; ahora son tres. Lo que la barra hacía vive en el armazón, en la
 * partición de la pantalla. Se conservan aquí, explícitamente, las dos
 * afirmaciones que **no** dependían de ella y que siguen siendo las que
 * importan: que la vista de la consola sigue **sin `preload`**, y que el
 * arranque aborta si dos particiones se igualan.
 */
describe("la vista de la consola sigue sin preload (3.5, 14.1)", () => {
  it("la página no tiene ninguna vía de hablarle a la cáscara", () => {
    const prefs = consoleWebPreferences();
    expect(prefs.partition).toBe(HUMAN_PARTITION);
    expect(prefs).not.toHaveProperty("preload");
    expect(prefs.contextIsolation).toBe(true);
    expect(prefs.nodeIntegration).toBe(false);
    expect(prefs.sandbox).toBe(true);
  });
});

describe("la pantalla de operar es la tercera partición (spec 003, 12.1, 12.3, 14.2)", () => {
  it("tres particiones distintas; la de la pantalla no persiste", () => {
    expect(new Set([HUMAN_PARTITION, AGENT_PARTITION, APP_PARTITION]).size).toBe(3);
    expect(APP_PARTITION.startsWith("persist:")).toBe(false);
    expect(() => assertPartitionsAreSeparate()).not.toThrow();
    // El arranque aborta si dos se igualan: el fallo de configuración más fácil
    // de cometer al refactorizar, cazado antes de que haya ninguna fuga.
    expect(() => assertPartitionsAreSeparate(HUMAN_PARTITION, AGENT_PARTITION, AGENT_PARTITION)).toThrow();
    expect(() => assertPartitionsAreSeparate(HUMAN_PARTITION, AGENT_PARTITION, "persist:app")).toThrow();
  });

  it("la pantalla tiene su preload, sandbox y aislamiento; la consola sigue sin preload", () => {
    const prefs = appWebPreferences("/ruta/app-preload.cjs");
    expect(prefs.partition).toBe(APP_PARTITION);
    expect(prefs.preload).toBe("/ruta/app-preload.cjs");
    expect(prefs.contextIsolation).toBe(true);
    expect(prefs.nodeIntegration).toBe(false);
    expect(prefs.sandbox).toBe(true);
    expect(consoleWebPreferences()).not.toHaveProperty("preload");
  });

  it("la pantalla no comparte partición con la persona: no ve sus cookies", () => {
    expect(APP_PARTITION).not.toBe(HUMAN_PARTITION);
    expect(sessionCookieNames(APP_PARTITION)).not.toContain("auphere_console_session");
  });
});
