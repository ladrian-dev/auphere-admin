import "dotenv/config";
import { defineConfig } from "drizzle-kit";

const url = process.env.NEXUS_CONSOLE_DATABASE_URL ?? "";
if (!url) throw new Error("Drizzle: set NEXUS_CONSOLE_DATABASE_URL before running drizzle-kit.");

// Only the ``console_auth`` schema. ``public`` is Alembic's; the console
// reads ``partner_memberships``/``partners`` from it but never migrates it.
export default defineConfig({
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url },
  schemaFilter: ["console_auth"],
  verbose: true,
  strict: true,
});
