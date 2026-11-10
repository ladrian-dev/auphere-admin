import { readFileSync } from "node:fs";
import { join } from "node:path";

import openapiTS, { astToString } from "openapi-typescript";

import { BANNER, emit } from "./_write.mts";

/**
 * Spec 031, D14: the app's types come from the API's own OpenAPI, filtered to
 * `/console/lite/*` and `/app/*` by `apps/api/scripts/export_openapi.py`. A
 * route that changes shape breaks `tsc` here, not a person's phone.
 */
const root = join(import.meta.dirname, "..");
const source = join(root, "src/api/openapi.json");
const target = join(root, "src/api/schema.gen.ts");

const ast = await openapiTS(JSON.parse(readFileSync(source, "utf8")), { alphabetize: true });
emit(
  target,
  `${BANNER}// Source: src/api/openapi.json (apps/api/scripts/export_openapi.py) · generator: scripts/gen-schema.ts\n\n${astToString(ast)}`,
);
