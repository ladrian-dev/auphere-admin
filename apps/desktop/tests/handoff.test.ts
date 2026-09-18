/**
 * Requisitos 9.4 y 9.5 — el traspaso al navegador, y la vuelta.
 *
 * El recorrido que documentó el anexo 04: «Elegir plan» y «Comprar saldo»
 * salían a Stripe **sin decir nada** (`main.ts:196-201`), y la ventana se
 * quedaba exactamente igual mientras el navegador se abría detrás. Al volver,
 * nada se releía: el plan seguía diciendo lo de antes hasta reiniciar.
 *
 * Tres cosas se comprueban aquí, todas en el módulo puro: reconocer que una
 * salida es un pago, contar la espera, y saber qué hay que releer al volver.
 */
import { describe, expect, it } from "vitest";

import {
  HANDOFF_STATES,
  type HandoffState,
  handoffKindFor,
  isWaitingHandoff,
  refetchOnReturn,
} from "../src/handoff-state.js";

describe("qué salidas son un traspaso, y de qué clase", () => {
  it("el proveedor de pago se reconoce por su dominio, no por adivinar", () => {
    expect(handoffKindFor("https://checkout.stripe.com/c/pay/cs_test_123")).toBe("payment");
    expect(handoffKindFor("https://billing.stripe.com/p/session/abc")).toBe("payment");
  });

  it("entrar con Google es otra cosa, y se cuenta distinto", () => {
    expect(handoffKindFor("https://accounts.google.com/o/oauth2/v2/auth?x=1")).toBe("sign_in");
  });

  it("cualquier otro enlace es una salida sin más: no se le inventa una vuelta", () => {
    // Un enlace a la documentación no tiene nada que releer al volver, y
    // tratarlo como un pago pondría a la aplicación a recargar el plan sola.
    expect(handoffKindFor("https://auphere.com/docs")).toBeNull();
  });

  it("y un dominio que sólo *contiene* el del proveedor no cuela", () => {
    expect(handoffKindFor("https://checkout.stripe.com.evil.example/pay")).toBeNull();
  });
});

describe("mientras la persona está fuera, la ventana espera (9.4)", () => {
  it("los estados son los mismos que los de la entrada: una sola forma de esperar", () => {
    expect([...HANDOFF_STATES]).toEqual(["idle", "esperando", "vuelto", "cancelada", "caducada", "error"]);
  });

  it("esperando es esperando; lo demás, no", () => {
    expect(isWaitingHandoff("esperando")).toBe(true);
    for (const state of ["idle", "vuelto", "cancelada", "caducada", "error"] as const) {
      expect(isWaitingHandoff(state as HandoffState)).toBe(false);
    }
  });
});

describe("al volver se relee lo que pudo cambiar (9.5)", () => {
  it("de un pago: el plan y el consumo, no la aplicación entera", () => {
    expect(refetchOnReturn("payment")).toEqual(["membership", "usage"]);
  });

  it("de una entrada: quién eres, que es lo único que cambió", () => {
    expect(refetchOnReturn("sign_in")).toEqual(["session"]);
  });

  it("y no se reinicia nada: releer no es recargar", () => {
    for (const kind of ["payment", "sign_in"] as const) {
      expect(refetchOnReturn(kind)).not.toContain("restart");
    }
  });
});
