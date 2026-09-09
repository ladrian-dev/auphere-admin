/**
 * Requisito 15.2 — la cáscara no guarda credenciales de backend.
 *
 * La consola de partner ya cumple esto —acuña tokens EdDSA de 60 s por llamada y
 * CI hace grep de `NEXUS_ADMIN_TOKEN` para que no se cuele—. Envolverla en una
 * aplicación de escritorio **no puede relajarlo**, y es justo donde más tienta:
 * en una app instalada, «guardo el token para no pedirlo cada vez» parece una
 * comodidad y es una llave en el disco de otra persona.
 */
import { describe, expect, it } from "vitest";

/**
 * Compuesto en tiempo de ejecución, no literal: un escáner de secretos marcaría
 * el literal como clave real y bloquearía el push — con razón en la forma, que
 * es justo lo que este test comprueba que se detecta.
 */
const ANTHROPIC_SHAPE = "sk" + "-ant-api03-" + "a".repeat(25);
const PEM_SHAPE = "-----BEGIN " + "RSA PRIVATE KEY-----";

import {
  CredentialPersistenceError,
  PERSISTABLE_KEYS,
  assertNoBackendCredential,
  persistableState,
} from "../src/shell-state.js";

describe("qué se puede guardar en disco (15.2)", () => {
  it("la lista de lo persistible es corta y no incluye secretos", () => {
    expect(PERSISTABLE_KEYS).not.toContain("token");
    expect(PERSISTABLE_KEYS).not.toContain("session");
    expect(PERSISTABLE_KEYS.length).toBeLessThanOrEqual(6);
  });

  it("solo sobrevive lo que está en la lista", () => {
    const state = persistableState({
      windowBounds: "800x600",
      workdir: "/Users/luis/proyecto",
      NEXUS_ADMIN_TOKEN: "no",
      sessionCookie: "tampoco",
    });
    expect(Object.keys(state).sort()).toEqual(["windowBounds", "workdir"]);
  });
});

describe("y si algo con forma de credencial se cuela, se levanta", () => {
  it.each([
    ["NEXUS_ADMIN_TOKEN", "cualquier-cosa"],
    ["windowBounds", ANTHROPIC_SHAPE],
    ["workdir", PEM_SHAPE],
  ])("%s con %s", (key, value) => {
    expect(() => assertNoBackendCredential({ [key]: value })).toThrow(CredentialPersistenceError);
  });

  it("un estado inocente pasa", () => {
    expect(() =>
      assertNoBackendCredential({ windowBounds: "800x600", workdir: "/Users/luis/p" }),
    ).not.toThrow();
  });
});
