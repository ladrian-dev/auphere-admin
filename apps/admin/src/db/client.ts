/**
 * Drizzle client used only by Better Auth and the seed-admin script.
 *
 * The application surface (server actions, server components) does NOT
 * read or write through this client — those go through the FastAPI
 * backend. Drizzle here is a thin glue for auth bookkeeping.
 *
 * The connection string is the same Postgres the backend uses; Drizzle
 * targets only the ``auth`` schema (see ``schema.ts``). We use the
 * ``postgres`` driver (not the asyncpg-style one) because Drizzle's
 * Node migration runner is synchronous over a pooled connection.
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import * as schema from "./schema";

declare global {
  var _nexus_admin_pg: ReturnType<typeof postgres> | undefined;
}

function buildClient() {
  const url = process.env.NEXUS_ADMIN_DATABASE_URL ?? process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "NEXUS_ADMIN_DATABASE_URL or DATABASE_URL must be set for the admin app",
    );
  }
  return postgres(url, { max: 5, prepare: false });
}

const sql = globalThis._nexus_admin_pg ?? buildClient();
if (process.env.NODE_ENV !== "production") {
  globalThis._nexus_admin_pg = sql;
}

export const db = drizzle(sql, { schema });
export { schema };
