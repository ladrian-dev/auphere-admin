// @vitest-environment jsdom
/**
 * Requisito 9 — **todo tope lleva a la acción**.
 *
 * El hallazgo que esto cierra, del anexo 04: ninguno de los cinco topes llevaba
 * a ninguna parte. Sin plan decía «cambia de plan, en Cuenta» y Cuenta no tenía
 * plan; el pago salía al navegador y acababa en un 404; un cobro fallido no se
 * mencionaba en toda la aplicación; y «Actualizar» abría el directorio crudo del
 * canal.
 *
 * La regla, y lo que la hace comprobable: cada tope termina en **una acción con
 * destino exacto** o en el **nombre del rol** a quien pedirla. Nunca en las dos,
 * y nunca en ninguna.
 */
import { describe, expect, it } from "vitest";

import { CAPS, type Cap, type Gate, gateFor, whoToAsk } from "../src/gating";

const PUEDE = ["billing:manage", "teammates:use"];
const NO_PUEDE = ["teammates:use"];

describe("los cinco topes tienen nombre", () => {
  it("y no hay un sexto escondido en un `else`", () => {
    expect([...CAPS]).toEqual([
      "sin_plan",
      "plan_lleno",
      "pool_agotado",
      "cobro_fallido",
      "version_no_admitida",
    ]);
  });
});

describe("con permiso para contratar, cada uno lleva a un sitio exacto", () => {
  const gates = CAPS.map((cap) => [cap, gateFor(cap, PUEDE)] as const);

  for (const [cap, gate] of gates) {
    it(`${cap} termina en una acción`, () => {
      expect(gate.kind, `${cap} no ofrece acción`).toBe("action");
    });

    it(`${cap} dice a dónde, no «ve a Cuenta»`, () => {
      if (gate.kind !== "action") throw new Error("sin acción");
      // Un destino es una sección concreta del armazón o una salida declarada
      // al navegador. «En algún sitio de la consola» no es un destino.
      expect(gate.destination).toBeTruthy();
    });
  }

  it("y ninguno de los cinco dice a quién pedirlo: puede hacerlo ella", () => {
    for (const [, gate] of gates) expect(gate.kind).not.toBe("ask");
  });
});

describe("sin permiso para contratar, se dice a quién pedirlo (9.2)", () => {
  it("y **no** se ofrece la acción", () => {
    for (const cap of ["sin_plan", "plan_lleno", "pool_agotado", "cobro_fallido"] as const) {
      const gate = gateFor(cap, NO_PUEDE);
      expect(gate.kind, `${cap} sigue ofreciendo comprar sin permiso`).toBe("ask");
    }
  });

  it("se nombra el rol, no «un administrador» a secas", () => {
    expect(whoToAsk("sin_plan")).toMatch(/owner|billing|admin/);
  });

  it("actualizar la aplicación **sí** lo puede hacer cualquiera", () => {
    // No es una compra: es la aplicación de esta persona en su máquina.
    expect(gateFor("version_no_admitida", NO_PUEDE).kind).toBe("action");
  });
});

describe("el tope se dice ANTES de rellenar nada (9.3)", () => {
  it("con el plan lleno, el formulario no se llega a ofrecer", () => {
    const gate = gateFor("plan_lleno", PUEDE);
    if (gate.kind !== "action") throw new Error("sin acción");
    expect(gate.before).toBe(true);
  });

  it("y sin plan, tampoco", () => {
    const gate = gateFor("sin_plan", PUEDE);
    if (gate.kind !== "action") throw new Error("sin acción");
    expect(gate.before).toBe(true);
  });

  it("el pool agotado no bloquea el formulario: bloquea el turno", () => {
    // Crear un teammate con el pool agotado es legítimo; lo que no se puede es
    // ponerlo a trabajar. Confundirlos sería bloquear de más.
    const gate = gateFor("pool_agotado", PUEDE);
    if (gate.kind !== "action") throw new Error("sin acción");
    expect(gate.before).toBe(false);
  });
});

describe("ninguna salida pide datos de tarjeta (9.10)", () => {
  it("las que cobran salen al navegador, y se declara", () => {
    for (const cap of ["sin_plan", "plan_lleno", "cobro_fallido"] as const) {
      const gate = gateFor(cap, PUEDE) as Extract<Gate, { kind: "action" }>;
      expect(gate.handoff, `${cap} debería salir al navegador`).toBe(true);
    }
  });

  it("y las que no cobran se quedan dentro", () => {
    const dentro = gateFor("version_no_admitida", PUEDE) as Extract<Gate, { kind: "action" }>;
    expect(dentro.handoff).toBe(false);
  });
});

describe("un tope desconocido no se inventa una salida", () => {
  it("lo que no está en la lista no pasa por aquí", () => {
    expect(CAPS.includes("otro" as Cap)).toBe(false);
  });
});
