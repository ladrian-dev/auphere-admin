#!/usr/bin/env node
/**
 * ADR-034 — el panel NO vuelve a tener base de datos.
 *
 * El 2026-08-19 ``admin.auphere.com`` se cayó porque resolvía la sesión con
 * Drizzle contra Postgres y la Aurora que sustituyó a Railway es privada:
 * una función de Vercel no la alcanza. La identidad se mudó a la API y el
 * panel se quedó sin ninguna credencial de base de datos.
 *
 * Esto es el cierre de esa puerta. Gemelo de
 * ``apps/console/scripts/check-no-admin-token.mjs``: una regla que se puede
 * violar sin querer merece un grep que la haga fallar en CI, no un párrafo
 * en un documento que nadie relee.
 *
 * Falla si en ``src/`` aparece Drizzle, un cliente de Postgres, Better Auth
 * o una variable de conexión.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("../src", import.meta.url).pathname;

/** Cada patrón dice QUÉ se prohíbe y por qué, para que el fallo se explique solo. */
const FORBIDDEN = [
  { re: /\bdrizzle-orm\b|\bdrizzle-kit\b|from ["']drizzle/, why: "Drizzle: el panel no habla con Postgres" },
  { re: /\bbetter-auth\b/, why: "Better Auth: la identidad vive en /admin/auth/* (ADR-034)" },
  { re: /\bNEXUS_ADMIN_DATABASE_URL\b/, why: "variable de conexión a Postgres" },
  { re: /process\.env\.DATABASE_URL\b/, why: "variable de conexión a Postgres" },
  { re: /from ["']postgres["']|from ["']pg["']/, why: "cliente de Postgres" },
];

/** @param {string} dir @returns {string[]} */
function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(ts|tsx|mjs|js)$/.test(name) ? [full] : [];
  });
}

const offences = [];
for (const file of walk(ROOT)) {
  const text = readFileSync(file, "utf8");
  text.split("\n").forEach((line, i) => {
    // Las menciones en comentarios son historia, no dependencias.
    const code = line.replace(/\/\/.*$/, "").replace(/^\s*\*.*$/, "");
    for (const { re, why } of FORBIDDEN) {
      if (re.test(code)) offences.push(`${file}:${i + 1}  ${why}\n    ${line.trim()}`);
    }
  });
}

if (offences.length > 0) {
  console.error("apps/admin ha vuelto a coger una dependencia de base de datos:\n");
  console.error(offences.join("\n"));
  console.error(
    "\nLa identidad del panel vive en la API (ADR-034). Si necesitas datos, pásalos por /admin/*.",
  );
  process.exit(1);
}
console.log("ok — apps/admin sigue sin base de datos");
