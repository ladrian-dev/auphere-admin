import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
// Vendored copy of `packages/ucm-schema/fixtures/` so the TS test suite
// stays self-contained inside the admin repo. The Python side keeps the
// original fixtures dir; both are derived from the UCM v1.0.0 spec and
// rarely change.
const fixturesDir = resolve(here, "..", "__fixtures__");

export const VALID = JSON.parse(
  readFileSync(resolve(fixturesDir, "valid.json"), "utf-8"),
);
export const INVALID = JSON.parse(
  readFileSync(resolve(fixturesDir, "invalid.json"), "utf-8"),
);
