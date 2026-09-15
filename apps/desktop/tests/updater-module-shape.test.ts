/**
 * De dónde sale `autoUpdater` — el fallo `updater-no-arranca` (2026-09-15).
 *
 * WHEN la cáscara arma el actualizador en un binario empaquetado y firmado
 * THEN el sistema DEBE obtener un `autoUpdater` definido del módulo de
 * `electron-updater`.
 *
 * En v0.1.0 y v0.1.1 no lo obtenía: `const { autoUpdater } = await
 * import("electron-updater")` daba `undefined` y la línea siguiente lanzaba un
 * `TypeError`, así que ninguna máquina llegó a preguntarle nunca al canal.
 *
 * ── Por qué este test sale a un subproceso, y no se "simplifica" ──────────
 *
 * **Vitest no puede reproducir este fallo.** Su interop de CommonJS expone
 * `autoUpdater` como exportación nombrada; el ESM de Node, que es lo que corre
 * dentro del `.app`, no lo hace — `cjs-module-lexer` es estático y no reconoce
 * el getter perezoso de `out/main.js:78`. Comprobado el 2026-09-15:
 *
 *     bajo vitest      → 'autoUpdater' in mod === true
 *     bajo node ESM    → 'autoUpdater' in mod === false
 *
 * Un test escrito con el `import` de vitest habría estado **verde antes del
 * arreglo**. Por eso la reproducción se ejecuta en un `node` de verdad.
 *
 * Y por eso el segundo test recorre el fuente en vez de llamar a la función:
 * leer el valor dispara el getter, que construye `MacUpdater` y necesita
 * `electron.app`, así que fuera de Electron lanza **por una causa distinta** —
 * un test que llamara acabaría en rojo siempre, y en verde por accidente en
 * cuanto alguien lo envolviera en un `try`. Es el mismo recurso que usan
 * `no-own-auth.test.ts` y `no-credentials-over-ipc.test.ts`.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const UPDATER = new URL("../src/electron/updater.ts", import.meta.url).pathname;

/** Lo mismo que hace el `.app`: ESM de Node, sin vitest por medio. */
function inRealNode(script: string): string {
  return execFileSync(process.execPath, ["--input-type=module", "-e", script], {
    cwd: new URL("..", import.meta.url).pathname,
    encoding: "utf8",
  }).trim();
}

describe("la forma real del módulo de electron-updater (Node ESM, no vitest)", () => {
  it("NO expone `autoUpdater` como exportación nombrada", () => {
    const out = inRealNode(
      `const m = await import("electron-updater");` +
        `console.log("autoUpdater" in m ? "presente" : "ausente");`,
    );
    // Si esto pasa a «presente», electron-updater publicó ESM o cambió el
    // getter: el rodeo por `default` dejó de hacer falta y hay que mirarlo.
    expect(out).toBe("ausente");
  });

  it("sí lo expone bajo `default`, que es de donde hay que sacarlo", () => {
    const out = inRealNode(
      `const m = await import("electron-updater");` +
        `console.log("autoUpdater" in (m.default ?? m) ? "presente" : "ausente");`,
    );
    expect(out).toBe("presente");
  });
});

describe("cómo lo carga la cáscara", () => {
  const source = readFileSync(UPDATER, "utf8");

  it("no desestructura `autoUpdater` directamente del import dinámico", () => {
    // La forma que rompió v0.1.0 y v0.1.1, en una sola expresión.
    expect(source).not.toMatch(/\{[^}]*\bautoUpdater\b[^}]*\}\s*=\s*await\s+import\(/);
  });

  it("pasa por `default` antes de leer `autoUpdater`", () => {
    expect(source).toMatch(/\.default\s*\?\?/);
  });
});
