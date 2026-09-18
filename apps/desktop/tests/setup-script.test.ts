/**
 * Requisito 8.6 — el guion de puesta en marcha dice **lo mismo** en las tres
 * superficies, y no pide algo que ya está hecho.
 *
 * Lo que el anexo 04 encontró leyendo los textos de las tres a la vez:
 *
 * * **«desde la barra de la aplicación»**, en siete sitios. Esa barra se retira
 *   con esta spec: mandar a alguien a una ventana que ya no existe es la peor
 *   instrucción posible, porque parece que la aplicación está rota;
 * * **«Instala la aplicación de escritorio, entra con tu cuenta y pide aquí un
 *   código»**, en el vacío de máquinas de la consola — leído **desde dentro de
 *   la aplicación de escritorio**, con la sesión ya iniciada. Dos de los tres
 *   pasos ya estaban hechos;
 * * el panel de Entorno decía a la vez «empareja la tuya desde la barra» y «Se
 *   empareja desde la consola», con un botón a la puesta en marcha. Dos
 *   instrucciones contradictorias para lo mismo.
 *
 * Esto se comprueba sobre los catálogos de texto, que es donde vive el guion.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const raiz = join(HERE, "..", "..", "..");
/**
 * Sin comentarios: aquí se cita la barra retirada para explicar qué sustituye
 * cada texto, y eso no es una instrucción que nadie vaya a leer en pantalla.
 */
const leer = (...p: string[]) =>
  readFileSync(join(raiz, ...p), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");

/** Los catálogos donde vive el guion de puesta en marcha. */
const CATALOGOS = [
  ["la aplicación", join("apps", "desktop", "src", "app", "i18n.ts")],
  ["la consola, puesto de trabajo", join("apps", "console", "src", "i18n", "lanes", "workstation.ts")],
  ["la consola, general", join("apps", "console", "src", "i18n", "messages.ts")],
] as const;

describe("nadie manda a la barra que se retira (8.6)", () => {
  for (const [nombre, fichero] of CATALOGOS) {
    it(`${nombre} no dice «desde la barra»`, () => {
      const texto = leer(...fichero.split("/"));
      const barra = texto.match(/(?:en|desde|de) la barra(?: de la aplicación)?/gi) ?? [];
      expect(barra, `${fichero} sigue mandando a la barra:\n${barra.join("\n")}`).toHaveLength(0);
    });

    it(`${nombre} tampoco en inglés`, () => {
      const texto = leer(...fichero.split("/"));
      const bar = texto.match(/(?:in|from) the app's bar|the app's bar/gi) ?? [];
      expect(bar, `${fichero}:\n${bar.join("\n")}`).toHaveLength(0);
    });
  }
});

describe("y nadie pide algo que la persona ya hizo", () => {
  it("la consola no dice «instala la aplicación de escritorio»", () => {
    // Se lee **dentro** de la aplicación de escritorio, con la sesión puesta.
    const texto = leer("apps", "console", "src", "i18n", "lanes", "workstation.ts");
    expect(texto).not.toMatch(/Instala la aplicación de escritorio/i);
    expect(texto).not.toMatch(/Install the desktop app/i);
  });

  it("ni «entra con tu cuenta» a quien ya entró", () => {
    const texto = leer("apps", "console", "src", "i18n", "lanes", "workstation.ts");
    expect(texto).not.toMatch(/entra con tu cuenta/i);
  });
});

describe("el guion dice lo mismo: el código se pide en la consola y se teclea en la aplicación", () => {
  it("la consola manda a la aplicación, sin nombrar una ventana que no existe", () => {
    const texto = leer("apps", "console", "src", "i18n", "lanes", "workstation.ts");
    expect(texto).toMatch(/aplicación de escritorio/);
  });

  it("y la aplicación dice dónde se pide, no «pídelo por ahí»", () => {
    const texto = leer("apps", "desktop", "src", "app", "i18n.ts");
    expect(texto).toMatch(/Puesto de trabajo|Workstation/);
  });
});
