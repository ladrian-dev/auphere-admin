import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import { env } from "@/lib/env";

import * as schema from "./schema";

/**
 * One pooled connection for the console: Better Auth bookkeeping
 * (``console_auth.*``) and the read-only membership lookup on
 * ``public.partner_memberships`` / ``public.partners``. Everything else
 * goes through the API with a per-request token (``lib/backend.ts``).
 *
 * The DB role should have: ALL on schema ``console_auth``; SELECT on
 * ``public.partner_memberships`` and ``public.partners``. Nothing else.
 */
declare global {
  var _nexus_console_pg: ReturnType<typeof postgres> | undefined;
}

function build() {
  return postgres(env().NEXUS_CONSOLE_DATABASE_URL, { max: 5, prepare: false });
}

const sql = globalThis._nexus_console_pg ?? build();
if (process.env.NODE_ENV !== "production") globalThis._nexus_console_pg = sql;

export const db = drizzle(sql, { schema });
export { schema, sql };
