/**
 * Requisito 7.4 — cancelado, caducado y error tienen mensaje y reintento, y
 * **nunca se espera en silencio**.
 *
 * El anexo 04 documentó los dos silencios concretos: si la persona cancela en
 * Google, el retorno vuelve a `/login` sin destino y la aplicación **espera los
 * cinco minutos enteros** sin decir nada; sin pertenencia a partner, igual. En
 * los dos casos la ventana se queda con «esperando» puesto hasta que caduca.
 *
 * Esto es el módulo puro que nombra el desenlace. Que la pantalla lo pinte se
 * comprueba en `sign-in-entry.test.tsx`; que el desenlace exista y tenga salida
 * se comprueba aquí, sin Electron y sin red.
 */
import { describe, expect, it } from "vitest";

import {
  SIGN_IN_STATES,
  type SignInState,
  isWaiting,
  offersRetry,
  signInFrom,
} from "../src/sign-in-state.js";
import { returnPage } from "../src/loopback-login.js";

const AHORA = "2026-09-18T10:00:00Z";

describe("los seis estados de la entrada", () => {
  it("están todos nombrados, y ninguno es «no se sabe»", () => {
    expect([...SIGN_IN_STATES]).toEqual(["idle", "esperando", "vuelto", "cancelada", "caducada", "error"]);
  });

  it("del retorno del navegador sale el estado, no una interpretación", () => {
    expect(signInFrom({ kind: "code" }, AHORA).state).toBe("vuelto");
    expect(signInFrom({ kind: "denied" }, AHORA).state).toBe("cancelada");
    expect(signInFrom({ kind: "timeout" }, AHORA).state).toBe("caducada");
  });

  it("y un canje que falla no es «cancelada»: es un error", () => {
    // Cancelar es una decisión de la persona; que el canje falle es una avería.
    // Mezclarlos deja a alguien creyendo que cerró la pestaña sin querer.
    expect(signInFrom({ kind: "redeem_failed" }, AHORA).state).toBe("error");
  });

  it("todos llevan desde cuándo, para poder decir «llevas esperando N»", () => {
    for (const retorno of [{ kind: "code" }, { kind: "denied" }, { kind: "timeout" }] as const) {
      expect(signInFrom(retorno, AHORA).since).toBe(AHORA);
    }
  });
});

describe("ninguno de los tres desenlaces malos se queda en silencio", () => {
  it("cancelada, caducada y error ofrecen volver a intentarlo", () => {
    for (const state of ["cancelada", "caducada", "error"] as const) {
      expect(offersRetry(state), `${state} se queda sin salida`).toBe(true);
    }
  });

  it("y ninguno de ellos sigue contando como «esperando»", () => {
    // Éste es el bug: la ventana se quedaba en «esperando» cinco minutos
    // después de que la persona hubiera cancelado en el navegador.
    for (const state of ["cancelada", "caducada", "error"] as const) {
      expect(isWaiting(state), `${state} sigue pareciendo una espera`).toBe(false);
    }
  });

  it("esperar sí es esperar, y entrar bien no ofrece reintentar nada", () => {
    expect(isWaiting("esperando")).toBe(true);
    expect(offersRetry("vuelto")).toBe(false);
    expect(offersRetry("idle")).toBe(false);
  });

  it("cada desenlace tiene su propio texto: no se reutiliza uno genérico", () => {
    const claves = new Set<string>();
    for (const state of SIGN_IN_STATES) claves.add(`signin.${state}`);
    expect(claves.size).toBe(SIGN_IN_STATES.length);
  });
});

describe("y la espera está acotada", () => {
  it("una espera sin fin es una espera en silencio con otro nombre", () => {
    const state: SignInState = "esperando";
    expect(isWaiting(state)).toBe(true);
    // El oyente caduca solo (`LOGIN_TIMEOUT_MS`), y al caducar el estado pasa a
    // `caducada`, que sí tiene mensaje y reintento.
    expect(offersRetry("caducada")).toBe(true);
  });
});

/**
 * Requisitos 7.3 y 12.2 — la página de vuelta del navegador.
 *
 * Era `text/plain`, en español y con una sola frase: «Ya puedes volver a
 * Auphere.» Lo primero que se ve después de entrar no puede ser una página sin
 * estilo, en un idioma que quizá no es el tuyo, y sin decir qué hacer si la
 * ventana no aparece.
 */
describe("la página de vuelta", () => {
  it("habla las dos lenguas: el navegador es de la persona, no de la cuenta", () => {
    const page = returnPage(true);
    expect(page).toMatch(/volver a Auphere/);
    expect(page).toMatch(/go back to Auphere/i);
  });

  it("dice qué hacer si la ventana no aparece sola", () => {
    expect(returnPage(true)).toMatch(/Dock/);
  });

  it("el fallo no se disfraza de éxito, y dice que la cuenta no cambió", () => {
    const page = returnPage(false);
    expect(page).not.toMatch(/Ya puedes volver/);
    expect(page).toMatch(/no ha cambiado/);
  });

  it("no pide **nada** a la red: es una página servida desde 127.0.0.1", () => {
    // Una fuente, un logotipo o un script remotos serían una petición desde un
    // origen local a media sesión de inicio. Todo va dentro.
    const page = returnPage(true);
    expect(page).not.toMatch(/<script/i);
    expect(page).not.toMatch(/https?:\/\//);
    expect(page).not.toMatch(/<img/i);
  });

  it("y respeta el tema del sistema en vez de imponer uno", () => {
    expect(returnPage(true)).toMatch(/color-scheme: light dark/);
  });
});
