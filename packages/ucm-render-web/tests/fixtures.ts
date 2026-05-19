/**
 * Convenience fixtures for the snapshot suite.
 *
 * Re-loads the JSON from the schema package so the snapshot tests share
 * one source of truth with the schema validators. ``parseUcm`` lives
 * here as a thin wrapper because the schema export is the runtime
 * Zod schema; we want already-typed values in tests.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { UCMMessageSchema, type UCMMessage } from "@nexus/ucm-schema";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "..", "..", "ucm-schema", "fixtures");

const raw = JSON.parse(
  readFileSync(resolve(fixturesDir, "valid.json"), "utf-8"),
) as Record<string, unknown>;

function parseUcm(input: unknown): UCMMessage {
  return UCMMessageSchema.parse(input);
}

export const FIXTURES: Record<string, UCMMessage> = Object.fromEntries(
  Object.entries(raw).map(([key, payload]) => [key, parseUcm(payload)]),
);
