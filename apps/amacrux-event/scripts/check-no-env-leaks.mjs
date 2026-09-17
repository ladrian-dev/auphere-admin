#!/usr/bin/env node
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { scan } from "./no-env-leaks-rules.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const violations = scan(root);
if (violations.length > 0) {
  console.error("check-no-env-leaks: fallos\n" + violations.map((v) => `  - ${v}`).join("\n"));
  process.exit(1);
}
console.log("check-no-env-leaks: ok");
