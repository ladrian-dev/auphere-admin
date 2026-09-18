/**
 * Requisitos 6.1, 6.3 y 6.6 — la versión nueva se **dice**, y la decide la
 * persona.
 *
 * El hallazgo del anexo 04: «se descarga en silencio y no se dice». La
 * aplicación tenía el ciclo entero montado —comprueba el canal, descarga,
 * instala al salir— y **nada de eso llegaba nunca a una pantalla**. El estado
 * `esperando_trabajo` de la barra existía en el tipo y no se pintaba jamás,
 * porque nadie lo emitía. Un aviso de actualización que sólo aparece en el
 * registro es exactamente igual que no tener aviso.
 *
 * Es un test estructural sobre el pegamento —montarlo de verdad exigiría
 * Electron y el canal— y se declara como tal. Lo que decide ya está probado
 * aparte, en `update-policy.test.ts`, sin Electron y sin red.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { decideUpdate } from "../src/update-policy.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (...parts: string[]) => readFileSync(join(HERE, "..", "src", ...parts), "utf8");
/** Sin comentarios: aquí se cita el código viejo para explicar lo que cambió. */
const sinComentarios = (code: string) => code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

const UPDATER = sinComentarios(read("electron", "updater.ts"));
const MAIN = sinComentarios(read("electron", "main.ts"));
const SURFACE = sinComentarios(read("electron", "app-surface.ts"));
const ARMAZON = sinComentarios(read("app", "shell", "update-banner.tsx"));

describe("la versión descargada sale del registro y llega a la pantalla", () => {
  it("el updater tiene por dónde contar lo que le pasa", () => {
    // Sin un puerto para anunciar, `log` es el único destino y nadie lee logs.
    expect(UPDATER).toMatch(/announce/);
  });

  it("y lo anuncia al descargar, no sólo al salir", () => {
    const descarga = UPDATER.slice(UPDATER.indexOf('"update-downloaded"'));
    expect(descarga.slice(0, 400)).toMatch(/announce\w*\(/);
  });

  it("el principal lo empuja al armazón por `app:update`", () => {
    expect(MAIN).toMatch(/announce:.*\n?.*app:update|pushApp\("app:update"/);
  });
});

describe("con trabajo vivo no se instala, y se dice", () => {
  it("la política ya lo decide: esperar, no instalar", () => {
    const decision = decideUpdate({
      build: "signed",
      activity: { liveSessions: 0, pendingApprovals: 2 },
      downloaded: { version: "1.2.0" },
      available: null,
    });
    expect(decision).toEqual({ kind: "wait", version: "1.2.0", reason: "busy" });
  });

  it("y ese «esperando» también se anuncia, que es lo que faltaba", () => {
    expect(UPDATER).toMatch(/esperando_trabajo/);
  });

  it("instalar a petición de la persona respeta lo mismo", () => {
    // R6.3: pedir instalar con trabajo vivo **no instala** y lo dice. La forma
    // del rechazo la fija el contrato: `{error: "busy"}`.
    expect(SURFACE).toMatch(/app:update\.install/);
    expect(UPDATER).toMatch(/error: "busy"/);
  });

  it("y el armazón lo pinta, en vez de dejar el botón como si no hiciera nada", () => {
    expect(ARMAZON).toMatch(/busy/);
  });
});

describe("la pantalla lo dice sin interrumpir (6.1)", () => {
  it("hay un banner del armazón para la versión nueva", () => {
    expect(ARMAZON).toMatch(/app:update|UpdateView|UpdateState/);
  });

  it("no es un diálogo: una versión nueva no interrumpe lo que estabas haciendo", () => {
    expect(ARMAZON).not.toMatch(/role="alertdialog"|showMessageBox/);
  });

  it("y nombra la versión: «hay una nueva» sin número no deja comprobar nada", () => {
    expect(ARMAZON).toMatch(/version/);
  });
});

describe("desde el menú se comprueba y se ve la versión (6.5)", () => {
  it("el panel «Acerca de» lleva la versión instalada", () => {
    expect(MAIN).toMatch(/setAboutPanelOptions/);
    expect(MAIN).toMatch(/applicationVersion: app\.getVersion\(\)/);
  });

  it("y la orden de menú cambia de significado en vez de haber una apagada", () => {
    // «Instalar» sin nada descargado no lleva a ninguna parte (§V): la misma
    // entrada comprueba, y sólo instala cuando hay algo que instalar.
    expect(MAIN).toMatch(/updateState\.state === "lista"/);
    expect(MAIN).toMatch(/m\.installUpdate/);
  });
});

describe("y no se reinicia por su cuenta (6.6)", () => {
  it("la instalación automática al salir está apagada", () => {
    expect(UPDATER).toMatch(/autoInstallOnAppQuit\s*=\s*false/);
  });

  it("`quitAndInstall` sólo se llama donde la persona ya decidió", () => {
    // Dos sitios y sólo dos: salir con la actualización lista —que es la
    // persona cerrando— y la orden explícita de instalar.
    const llamadas = [...UPDATER.matchAll(/quitAndInstall\(/g)];
    expect(llamadas.length).toBeGreaterThan(0);
    expect(llamadas.length).toBeLessThanOrEqual(2);
  });

  it("no hay ningún `relaunch` suelto", () => {
    expect(UPDATER).not.toMatch(/app\.relaunch\(/);
    expect(MAIN).not.toMatch(/app\.relaunch\(/);
  });
});
