/** Shared fixture loader — same JSON as ucm-render-web. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { UCMMessageSchema, type UCMMessage } from "@nexus/ucm-schema";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "..", "..", "ucm-schema", "fixtures");

const raw = JSON.parse(
  readFileSync(resolve(fixturesDir, "valid.json"), "utf-8"),
) as Record<string, unknown>;

export const FIXTURES: Record<string, UCMMessage> = Object.fromEntries(
  Object.entries(raw).map(([key, payload]) => [
    key,
    UCMMessageSchema.parse(payload),
  ]),
);
