/**
 * Requisito 2.1 — la pantalla se sirve entera a sí misma.
 *
 * Dos cosas que hasta la spec 010 no eran ciertas y que aquí quedan fijadas:
 *
 * * **La vista de la aplicación declara política de contenido.** La del puesto
 *   la tenía desde la spec 002; ésta no. Era el hueco por el que podía entrar
 *   cualquier cosa remota sin que nadie se enterara.
 * * **No hay ningún origen remoto.** Ni fuentes de Google, ni iconos por URL,
 *   ni scripts de terceros. Las fuentes de marca viajan dentro del paquete,
 *   que es lo que hace que la ventana se vea igual sin conexión.
 *
 * El test lee los ficheros fuente, no el empaquetado: así falla en el momento
 * en que alguien escribe la URL, no tres pasos después.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = join(HERE, "..", "src", "app");

const html = readFileSync(join(APP, "index.html"), "utf8");
const styles = readFileSync(join(APP, "styles.css"), "utf8");

/** El contenido de la etiqueta `http-equiv="Content-Security-Policy"`. */
function policy(): string {
  const match = html.match(/http-equiv="Content-Security-Policy"\s+content="([^"]+)"/s);
  return match?.[1] ?? "";
}

/** Las directivas, normalizadas a `{nombre: [valores]}`. */
function directives(): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const part of policy().split(";")) {
    const [name, ...values] = part.trim().split(/\s+/);
    if (name) out[name] = values;
  }
  return out;
}

describe("la vista de la aplicación declara su política de contenido", () => {
  it("la etiqueta existe", () => {
    expect(policy()).not.toBe("");
  });

  it("cierra por defecto y no deja escapar nada por omisión", () => {
    expect(directives()["default-src"]).toEqual(["'none'"]);
  });

  it("scripts y fuentes solo de la propia aplicación", () => {
    expect(directives()["script-src"]).toEqual(["'self'"]);
    expect(directives()["font-src"]).toEqual(["'self'"]);
  });

  it("la pantalla no habla con la red: eso es del proceso principal", () => {
    expect(directives()["connect-src"]).toEqual(["'none'"]);
  });

  it("ninguna directiva admite un origen remoto", () => {
    for (const [name, values] of Object.entries(directives())) {
      for (const value of values) {
        expect(value, `${name} permite ${value}`).not.toMatch(/^https?:/);
        expect(value, `${name} permite ${value}`).not.toMatch(/\*/);
      }
    }
  });
});

describe("no entra nada por la red en tiempo de ejecución", () => {
  it("la hoja de estilos no importa ninguna URL", () => {
    expect(styles).not.toMatch(/@import\s+url\(/i);
    expect(styles).not.toMatch(/https?:\/\//);
  });

  it("la página no enlaza ningún recurso remoto", () => {
    expect(html).not.toMatch(/(?:src|href)="https?:\/\//i);
  });

  it("las fuentes de marca se empaquetan, no se piden", () => {
    expect(styles).toMatch(/@fontsource-variable\/inter-tight/);
    expect(styles).toMatch(/@fontsource-variable\/jetbrains-mono/);
    // Y quedan conectadas a los tokens, que es lo que hace que se usen.
    expect(styles).toMatch(/--font-inter-tight:\s*"Inter Tight Variable"/);
    expect(styles).toMatch(/--font-jetbrains-mono:\s*"JetBrains Mono Variable"/);
  });
});
