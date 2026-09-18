/**
 * Requisito 5.4 — la misma cifra en las cuatro superficies.
 *
 * El hallazgo que esto cierra: la lista lateral, el icono de la aplicación, el
 * icono de la barra del sistema y Pendientes contaban con **tres reglas
 * distintas**. Una incluía lo informativo, otra no, otra cortaba en nueve. La
 * misma ventana podía decir 4, 3 y 3 sobre el mismo hecho, y quien lo ve una
 * vez deja de creerse el número para siempre.
 *
 * El test no comprueba que las cuatro «coincidan por casualidad» con una lista
 * de ejemplo: comprueba que **preguntan a la misma función**. Dos recuentos que
 * hoy dan lo mismo son dos recuentos que mañana divergen.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { badgeCount } from "../src/notifications-policy.js";
import { trayBadge } from "../src/tray-badge.js";
import { badgeText, countWaiting, waitingFrom } from "../src/waiting.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const src = (...parts: string[]) => readFileSync(join(HERE, "..", "src", ...parts), "utf8");

const item = (level: "critico" | "aviso" | "informativo", can_decide = true) => ({
  action_id: `a-${level}-${can_decide}`,
  teammate_id: "t-1",
  since: "2026-09-17T10:00:00Z",
  level,
  can_decide,
});

/** Una bandeja con de todo: dos que esperan y dos que no. */
const BANDEJA = [item("critico"), item("aviso"), item("informativo"), item("critico", false)];

describe("una definición, no cuatro", () => {
  it("la cifra es la misma se pregunte desde donde se pregunte", () => {
    const esperada = 2;
    expect(countWaiting(BANDEJA)).toBe(esperada);
    // El icono de la aplicación (`app.setBadgeCount`), vía la política de avisos.
    expect(badgeCount(BANDEJA.map((i) => ({ ...i, teammate: "Sofía", title: "x" })))).toBe(esperada);
    // El icono de la barra del sistema.
    expect(trayBadge(BANDEJA)).toBe(String(esperada));
    // Y la lista lateral, que pinta la cifra entera.
    expect(badgeText(waitingFrom(BANDEJA), { cap: false })).toBe(String(esperada));
  });

  it("lo informativo no cuenta en ninguna: no espera nada", () => {
    const solo = [item("informativo"), item("informativo")];
    expect(countWaiting(solo)).toBe(0);
    expect(trayBadge(solo)).toBe("");
    expect(badgeCount(solo.map((i) => ({ ...i, teammate: "Sofía", title: "x" })))).toBe(0);
  });

  it("lo que esta persona no puede decidir tampoco la persigue por el Dock", () => {
    const ajeno = [item("critico", false)];
    expect(countWaiting(ajeno)).toBe(0);
    expect(trayBadge(ajeno)).toBe("");
  });
});

describe("y el tope es presentación, no otra cifra", () => {
  it("los iconos cortan en «9+»; la cifra sigue siendo la cifra", () => {
    const muchas = Array.from({ length: 12 }, () => item("critico"));
    expect(countWaiting(muchas)).toBe(12);
    expect(trayBadge(muchas)).toBe("9+");
    // Donde hay sitio se escribe entera: la lista lateral no es un icono.
    expect(badgeText(waitingFrom(muchas), { cap: false })).toBe("12");
  });
});

describe("nadie vuelve a contar por su cuenta", () => {
  /** Los ficheros que cada superficie usa para decir su número. */
  const superficies = [
    ["la política de avisos y el icono de la aplicación", join("notifications-policy.ts")],
    ["el icono de la barra del sistema", join("tray-badge.ts")],
    ["la pantalla", join("app", "App.tsx")],
  ] as const;

  for (const [nombre, fichero] of superficies) {
    it(`${nombre} pregunta a \`waiting.ts\``, () => {
      const codigo = src(...fichero.split("/"));
      expect(codigo, `${fichero} no importa el derivado único`).toMatch(/from "[./]*(\.\.\/)?waiting(\.js)?"/);
    });

    it(`${nombre} no filtra por nivel por su cuenta`, () => {
      // Sin comentarios: aquí se cita el recuento viejo para explicar el cambio.
      const codigo = src(...fichero.split("/"))
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/\/\/.*$/gm, "");
      // `level !== "informativo"` era literalmente la tercera regla suelta.
      expect(codigo, `${fichero} vuelve a decidir qué cuenta`).not.toMatch(/level\s*!==\s*"informativo"/);
    });
  }
});

describe("al decidir, las cuatro bajan a la vez", () => {
  it("porque las cuatro leen la misma lista, no una copia cada una", () => {
    const antes = BANDEJA;
    const despues = antes.filter((i) => i.action_id !== item("critico").action_id);
    const cifras = (lista: typeof antes) => [
      countWaiting(lista),
      badgeCount(lista.map((i) => ({ ...i, teammate: "Sofía", title: "x" }))),
      Number(trayBadge(lista) || 0),
      Number(badgeText(waitingFrom(lista), { cap: false }) || 0),
    ];
    expect(new Set(cifras(antes)).size).toBe(1);
    expect(new Set(cifras(despues)).size).toBe(1);
    expect(cifras(despues)[0]).toBe(cifras(antes)[0]! - 1);
  });
});
