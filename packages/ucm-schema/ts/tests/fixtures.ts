import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "..", "..", "fixtures");

export const VALID = JSON.parse(
  readFileSync(resolve(fixturesDir, "valid.json"), "utf-8"),
);
export const INVALID = JSON.parse(
  readFileSync(resolve(fixturesDir, "invalid.json"), "utf-8"),
);
