/**
 * Requisito 3.1 — sin red, la aplicación arranca igual.
 *
 * Éste es uno de los cinco fallos que impiden completar el recorrido básico, y
 * el más silencioso: la puesta en marcha **esperaba** a que la consola remota
 * cargara, y si no había red la promesa se rechazaba y `bootstrap()` se abortaba
 * entero. Con ella se caían el veredicto de sesión, el vigilante de Pendientes
 * y el latido. La persona veía esqueletos para siempre, sin un solo mensaje.
 *
 * Lo que se comprueba aquí es la **secuencia**: que la carga de la consola no
 * está delante de nada de lo local, y que un fallo suyo se recoge en vez de
 * propagarse. Es un test estructural sobre el arranque —levantar Electron para
 * esto costaría más de lo que aporta— y se declara como tal.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const FUENTE = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8");

/**
 * El código, **sin comentarios**.
 *
 * Los comentarios de este arranque explican lo que se quitó citando el código
 * viejo, así que buscar patrones sobre el fichero entero encuentra el ejemplo
 * en vez del código. Es un tropiezo que ya tuvo este test.
 */
const MAIN = FUENTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

const at = (needle: string): number => {
  const index = MAIN.indexOf(needle);
  expect(index, `no encuentro «${needle}» en el arranque`).toBeGreaterThan(-1);
  return index;
};

describe("la consola no bloquea la puesta en marcha", () => {
  it("la carga de la consola no se espera antes de lo local", () => {
    // Si vuelve a aparecer un `await` sobre `loadURL`, todo lo de abajo queda
    // detrás de la red otra vez.
    expect(MAIN).not.toMatch(/await\s+consoleView\.webContents\.loadURL/);
  });

  it("su fallo se recoge y se anota, no se propaga", () => {
    const inicio = at("loadURL(CONSOLE_URL)");
    expect(MAIN.slice(inicio, inicio + 400)).toMatch(/catch/);
  });

  it("el veredicto de sesión se evalúa aunque la consola no esté", () => {
    // Se evalúa después de montar el armazón y **sin** esperar a la consola:
    // la carga de la consola va por su cuenta, sin `await` delante.
    expect(at("gate.evaluate()")).toBeGreaterThan(at("appView.webContents.loadFile"));
    expect(MAIN.slice(at("loadURL(CONSOLE_URL)") - 120, at("loadURL(CONSOLE_URL)"))).not.toMatch(/await\s*$/);
  });

  it("la ventana se muestra con el armazón montado, sin esperar a la red", () => {
    // El `window.show()` del arranque, no el de traer la ventana al frente
    // desde la bandeja: se busca **después** de cargar la vista local.
    const montaje = at("appView.webContents.loadFile");
    const mostrar = MAIN.indexOf("window.show()", montaje);
    expect(mostrar, "el arranque ya no muestra la ventana").toBeGreaterThan(-1);
    expect(mostrar).toBeLessThan(at("loadURL(CONSOLE_URL)"));
  });
});

describe("sin conexión se dice, y se puede reintentar", () => {
  it("el estado de conectividad se empuja a la pantalla", () => {
    expect(MAIN).toMatch(/app:connectivity/);
  });

  it("un fallo de red no se convierte en «no hay sesión»", () => {
    // La conversión vivía en `session-gate.ts` y ya no está; aquí se comprueba
    // que el arranque no la reintroduce por su cuenta.
    expect(MAIN).not.toMatch(/kind:\s*"stop",\s*reason:\s*"anonymous"/);
  });
});
