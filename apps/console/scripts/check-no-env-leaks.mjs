#!/usr/bin/env node
/**
 * CI guard (Sec 0.1): partner-facing console copy must not name
 * NEXUS_ / LITELLM_ / sk- / NEXUS_META_APP_ID. Server env schemas
 * and comments are out of scope — this walks i18n copy only.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("../src/i18n", import.meta.url).pathname;
const SKIP = new Set(["__tests__", "node_modules"]);
const NEEDLES = ["NEXUS_", "LITELLM_", "sk-", "NEXUS_META_APP_ID"];
const offenders = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(name)) {
      const text = readFileSync(p, "utf8");
      for (const needle of NEEDLES) {
        if (text.includes(needle)) offenders.push(relative(root, p) + ":" + needle);
      }
    }
  }
}
walk(root);
if (offenders.length) {
  console.error("partner-facing i18n must not name env/proxy/secrets:\n  " + offenders.join("\n  "));
  process.exit(1);
}
console.log("ok: no NEXUS_/LITELLM_/sk- in apps/console i18n copy");
