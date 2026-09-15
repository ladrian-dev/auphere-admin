/**
 * Qué entra en el paquete — el fallo `paquete-se-traga-su-propia-salida`.
 *
 * WHEN electron-builder empaqueta la aplicación
 * THEN el sistema NO DEBE incluir en el paquete la salida del propio
 * empaquetador.
 *
 * En v0.1.0 y v0.1.1 sí la incluía: `directories.output` no estaba declarado
 * —por defecto `dist`— y `files` decía `dist/**`. El asar de arm64 se llevó una
 * copia entera de Electron (320 MB de `dist/`), y el de x64 se llevó además la
 * aplicación de arm64 ya firmada **y un `.dmg` a medio escribir de 987 MB**,
 * porque las dos arquitecturas se solapan en el tiempo. 1,98 GB de asar.
 *
 * **No se prueba con globs negativos y por eso este test no los admite.** Entre
 * lo que se coló estaba `dist/ziGLCl5u`: un temporal de 32 MB con nombre
 * aleatorio y sin patrón. Lo que no tiene forma no se puede excluir por forma;
 * la única defensa es que la salida no viva debajo de lo que se empaqueta.
 *
 * Son tests de configuración porque el fallo es de configuración: no construyen
 * nada, y por eso pueden correr en cada push.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const HERE = new URL("../", import.meta.url).pathname;
const pkg = JSON.parse(readFileSync(`${HERE}package.json`, "utf8")) as {
  build: { files: string[]; directories?: { output?: string }; mac?: unknown };
};
const workflow = readFileSync(`${HERE}../../.github/workflows/release-desktop.yml`, "utf8");

/** Lo que electron-builder usa si nadie lo declara. */
const outputDir = pkg.build.directories?.output ?? "dist";

describe("el paquete no se traga su propia salida", () => {
  it("ningún patrón de `files` alcanza el directorio de salida", () => {
    const reach = pkg.build.files.filter((pattern) => {
      const root = pattern.replace(/^!/, "").split("/")[0];
      return root === outputDir;
    });
    expect(reach).toEqual([]);
  });

  it("el directorio de salida está declarado y no se deja al azar", () => {
    // Dejarlo por defecto es lo que puso la salida dentro del árbol empaquetado.
    // Declararlo es lo que hace que el test de arriba signifique algo mañana.
    expect(pkg.build.directories?.output).toBeTruthy();
  });
});

/**
 * T045 (a) de la spec 008 — `docs/pendientes-tras-el-go-live.md` §2.
 *
 * Electron 44 exige macOS 13 Ventura: Chromium dejó de soportar Monterey, y
 * afecta sobre todo a los Intel, que es donde más gente se quedó en macOS 12.
 * Sin el campo, el `.dmg` **deja instalar** en un Mac que luego no puede abrir
 * la aplicación y no dice por qué. Con él, macOS lo bloquea antes de copiar
 * nada y nombra la versión que hace falta.
 */
describe("el paquete dice qué macOS necesita", () => {
  it("declara `minimumSystemVersion`, y es 13 o más", () => {
    const declared = (pkg.build.mac as { minimumSystemVersion?: string } | undefined)
      ?.minimumSystemVersion;
    expect(declared).toBeTruthy();
    expect(Number.parseInt(declared ?? "0", 10)).toBeGreaterThanOrEqual(13);
  });
});

/**
 * La otra mitad, y existe por la historia de este repositorio: la tubería se ha
 * roto dos veces por declarar algo en un sitio y no en el otro, con la suite sin
 * correr en local (`CLAUDE.md`). Mover la salida sin tocar el workflow no rompe
 * la aplicación — deja de publicarla, que se nota más tarde y peor.
 */
describe("la cadena de publicación mira donde la salida está", () => {
  const paths = [...workflow.matchAll(/apps\/desktop\/([A-Za-z0-9_-]+)[/\s]/g)].map((m) => m[1]);

  it("el workflow nombra algún directorio de salida", () => {
    expect(paths.length).toBeGreaterThan(0);
  });

  it("todas las rutas del workflow apuntan al directorio declarado", () => {
    const wrong = [...new Set(paths)].filter((p) => p !== outputDir);
    expect(wrong).toEqual([]);
  });
});
