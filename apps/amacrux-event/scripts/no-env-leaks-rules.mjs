import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * Reglas compartidas por `check-no-env-leaks.mjs` (CLI) y el test de no
 * acoplamiento. Solo `src/lib/env.server.ts` y `src/app/api/**` pueden
 * nombrar secretos; nada en `src/` puede importar del resto del monorepo.
 */
export const SECRET_PATTERN = /RESEND_API_KEY|LEADS_TO|LEADS_FROM|SUPABASE_[A-Z_]+|LEADS_WEBHOOK_[A-Z_]+|NEXUS_[A-Z_]+|\bsk_(live|test)_/;
export const COUPLING_PATTERN = /from\s+["'](@nexus\/|\.\.\/\.\.\/(api|worker|console|admin)\/|.*packages\/ui)/;

export function isSecretAllowed(relPath) {
  return relPath === "src/lib/env.server.ts" || relPath.startsWith("src/app/api/");
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|tsx|mjs|js)$/.test(entry)) out.push(full);
  }
  return out;
}

export function scan(root) {
  const violations = [];
  for (const file of walk(join(root, "src"))) {
    const rel = relative(root, file);
    const text = readFileSync(file, "utf8");
    if (!isSecretAllowed(rel) && SECRET_PATTERN.test(text)) violations.push(`${rel}: nombra un secreto de servidor`);
    if (COUPLING_PATTERN.test(text)) violations.push(`${rel}: importa del resto del monorepo`);
  }
  return violations;
}
