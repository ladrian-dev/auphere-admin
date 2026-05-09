/**
 * Drizzle Kit config — drives ``pnpm db:generate`` (emits SQL migrations
 * under ``./drizzle``) and ``pnpm db:push`` (applies them).
 *
 * Targets only the ``auth`` schema; the application's ``public`` schema
 * is owned by Alembic and must never be touched here.
 */

import "dotenv/config";
import { defineConfig } from "drizzle-kit";

const url =
  process.env.NEXUS_ADMIN_DATABASE_URL ?? process.env.DATABASE_URL ?? "";

if (!url) {
  throw new Error(
    "Drizzle: set NEXUS_ADMIN_DATABASE_URL or DATABASE_URL before running drizzle-kit.",
  );
}

export default defineConfig({
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url },
  schemaFilter: ["auth"],
  verbose: true,
  strict: true,
});
