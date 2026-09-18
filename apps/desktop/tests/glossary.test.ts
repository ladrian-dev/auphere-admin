/**
 * Requisito 12 — **un solo glosario**, en las dos superficies y en los dos
 * idiomas.
 *
 * Lo que la investigación encontró leyendo los catálogos a la vez: al mismo
 * interlocutor se le llamaba «el Companion» en el cajón de la consola y
 * «teammate» en la aplicación, en la misma ventana. Y el pool semanal aparecía
 * como «tope mensual», «consumo», «presupuesto» y «pool» según quién escribiera.
 *
 * Un producto que se llama a sí mismo de tres maneras obliga a cada persona a
 * mantener su propia tabla de equivalencias.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const raiz = join(HERE, "..", "..", "..");
const leer = (...p: string[]) =>
  readFileSync(join(raiz, ...p), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");

const APP = leer("apps", "desktop", "src", "app", "i18n.ts");
const CUI = leer("packages", "companion-ui", "src", "messages.ts");

describe("al interlocutor se le llama por su nombre", () => {
  it("la aplicación no dice «Companion» en ningún texto", () => {
    // Dentro de la aplicación de escritorio, quien trabaja para ti es un
    // **teammate**. «Companion» es el nombre del cajón de la consola.
    const apariciones = APP.match(/Companion/g) ?? [];
    expect(apariciones, `«Companion» en la aplicación: ${apariciones.length}`).toHaveLength(0);
  });
});

describe("el pool semanal se llama siempre igual", () => {
  it("la aplicación no habla de un tope «mensual»", () => {
    // El pool es **semanal** desde la spec 004. «Mensual» quedó de antes y
    // dice algo falso sobre cuándo vuelve.
    const apariciones = APP.match(/tope mensual|mensual/gi) ?? [];
    expect(apariciones, `«mensual» en la aplicación: ${apariciones.join(", ")}`).toHaveLength(0);
  });

  it("y el paquete compartido tampoco", () => {
    const apariciones = CUI.match(/tope mensual/gi) ?? [];
    expect(apariciones, `«tope mensual» en el paquete: ${apariciones.length}`).toHaveLength(0);
  });
});

describe("las dos lenguas dicen lo mismo, y todo está traducido", () => {
  it("ninguna entrada de la aplicación se quedó con el español en el inglés", () => {
    const iguales: string[] = [];
    for (const match of APP.matchAll(/"([\w.]+)":\s*\{\s*es:\s*(".*?"),\s*en:\s*(".*?")\s*\}/g)) {
      const [, clave, es, en] = match;
      // Los nombres propios coinciden a propósito («Teammates», «Auphere»).
      if (es === en && !/^"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ ]*"$/.test(es!)) iguales.push(clave!);
    }
    expect(iguales, `sin traducir:\n${iguales.join("\n")}`).toHaveLength(0);
  });
});
