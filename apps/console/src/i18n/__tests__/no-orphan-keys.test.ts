import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { workstationMessages } from "../lanes/workstation";

/**
 * Ninguna clave del carril del puesto de trabajo sin quien la pida.
 *
 * **Esto existe por un defecto real.** La spec 012 retiró el diálogo de
 * emparejamiento y dejó vivas sus doce claves `ws.pair.*`, más tres textos que
 * ya mentían. Nada se puso rojo: una clave huérfana no rompe el `tsc`, no rompe
 * el `eslint` y no rompe ningún test de render, porque nadie la renderiza.
 * Sobrevivió a dos tareas que la daban por hecha y se descubrió por casualidad,
 * al caer otro test al lado.
 *
 * Doce textos muertos no son un problema de tamaño: son doce frases que
 * describen un producto que ya no existe, esperando a que alguien las lea y
 * crea que sí. Es §V —la pantalla no miente— un paso antes de la pantalla.
 *
 * **Por qué solo este carril, dicho sin adornos.** El mismo barrido sobre el
 * diccionario entero devuelve **293 claves huérfanas más**, repartidas por casi
 * todos los carriles y con un bloque `companion.*` duplicado entre la consola y
 * `packages/companion-ui`. Limpiar eso es trabajo propio, con su propio riesgo,
 * y no cabe dentro de la spec 012 — está anotado en la KB. Lo que no se puede
 * hacer es fingir que el barrido pasa: o vigila de verdad algo acotado, o no
 * vigila nada. Vigila el carril que acaba de fallar, y dice cuánto queda fuera.
 *
 * **Los prefijos dinámicos se descubren, no se declaran.** Media consola arma
 * claves en tiempo de ejecución (`ws.setup.step.${'$'}{s.key}`), y una lista de
 * excepciones escrita a mano se pudre en silencio: cada prefijo que alguien
 * olvide quitar tapa todas las claves que cuelgan de él. Aquí se leen del
 * propio código, así que la lista no puede quedarse vieja sin que el código
 * cambie con ella.
 */
const SRC = join(import.meta.dirname, "..", "..");
const LANES = join(SRC, "i18n");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      // Los carriles son la definición, no el uso; los tests tampoco cuentan
      // como uso: una clave que solo pide su propio test está igual de muerta.
      if (full === LANES || entry === "__tests__") return [];
      return sourceFiles(full);
    }
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

const corpus = sourceFiles(SRC)
  .map((f) => readFileSync(f, "utf8"))
  .join("\n");

/** `t("ws.machines.title")` — la clave entera, tal cual. */
const literal = new Set(Array.from(corpus.matchAll(/["'`]([\w.-]+)["'`]/g), (m) => m[1]!));

/** `` t(`ws.setup.step.${x}`) `` — lo que hay antes de la interpolación. */
const prefixes = Array.from(new Set(Array.from(corpus.matchAll(/`([\w.-]*\.)\$\{/g), (m) => m[1]!)));

describe("claves del puesto de trabajo sin dueño", () => {
  it("los prefijos dinámicos se leen del código, no de una lista", () => {
    // Si esto baja a cero, el descubrimiento dejó de funcionar y el test de
    // abajo pasaría a dar falsos positivos en masa.
    expect(prefixes.length).toBeGreaterThan(10);
  });

  it("ninguna clave se queda sin quien la pida", () => {
    const orphans = Object.keys(workstationMessages).filter(
      (key) => !literal.has(key) && !prefixes.some((p) => key.startsWith(p)),
    );
    expect(orphans, `claves que no pide nadie: ${orphans.join(", ")}`).toEqual([]);
  });
});
