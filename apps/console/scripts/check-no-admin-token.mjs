#!/usr/bin/env node
/**
 * CI guard (CP-03 acceptance): the console must not reference
 * NEXUS_ADMIN_TOKEN anywhere. Exit 1 with the offending files otherwise.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const SKIP = new Set(["node_modules", ".next", "drizzle", "scripts"]);
const offenders = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(ts|tsx|js|mjs|json|env(\..*)?|md)$/.test(name) && !name.endsWith(".lock")) {
      if (readFileSync(p, "utf8").includes("NEXUS_ADMIN_TOKEN")) offenders.push(relative(root, p));
    }
  }
}
walk(root);
if (offenders.length) {
  console.error("apps/console must never reference NEXUS_ADMIN_TOKEN:\n  " + offenders.join("\n  "));
  process.exit(1);
}
console.log("ok: no NEXUS_ADMIN_TOKEN in apps/console");
