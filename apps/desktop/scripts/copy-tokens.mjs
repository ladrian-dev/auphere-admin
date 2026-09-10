/**
 * Copia los tokens del sistema de diseño al bundle de la barra — Requisito 12.5.
 *
 * `@nexus/ui` vive en el workspace raíz y `apps/desktop` en el suyo, así que no
 * se importa: se copia en el build. Y **no se descarga en tiempo de ejecución**:
 * la barra tiene que pintar igual sin red, que es justo cuando más se mira.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../../../packages/ui/src/styles/tokens.css");
const target = resolve(here, "../src/bar/tokens.css");
mkdirSync(dirname(target), { recursive: true });

// La paleta y los tokens semánticos viven en `@theme { … }`, que solo entiende
// Tailwind: un navegador ignora el bloque entero y `--color-bg` no resuelve. La
// barra no pasa por Tailwind, así que ese primer bloque se vuelve `:root { … }`
// (son propiedades CSS normales). `@theme inline` es el espejo de utilidades y
// se deja: el navegador lo ignora sin daño. El puente `:root` / `[data-theme]`
// de shadcn queda intacto y es el que la barra consume para los colores.
const css = readFileSync(source, "utf8").replace(/^@theme \{$/m, ":root {");
writeFileSync(target, css);
console.log(`tokens: ${source} → ${target} (@theme → :root)`);
