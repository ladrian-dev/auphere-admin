import { z } from "zod";

/**
 * Validated server environment. Read once, fail loudly at boot: a console
 * that starts without its signing key would produce 401s that look like a
 * backend problem. There is deliberately NO static admin credential here —
 * ``scripts/check-no-admin-token.mjs`` (CI) fails if the admin token name
 * ever appears in this app.
 *
 * There is also NO database URL any more (ADR-032): identity lives in the
 * API, this app reaches Postgres never. That is what lets the console run
 * on Vercel while Aurora stays private.
 */
const schema = z.object({
  NEXUS_BACKEND_URL: z.string().url().default("http://localhost:8000"),
  NEXUS_CONSOLE_ORIGIN: z.string().url().default("http://localhost:3110"),
  NEXUS_CONSOLE_JWT_PRIVATE_KEY: z.string().min(1),
  NEXUS_CONSOLE_JWT_ISSUER: z.string().default("nexus-console"),
  NEXUS_CONSOLE_JWT_AUDIENCE: z.string().default("nexus-api"),
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  // Lane channels (CP-17): Meta Embedded Signup. Read on the server and
  // handed to the client component as props — no NEXT_PUBLIC_ inlining, so
  // a dev/staging Meta app is a redeploy, not a rebuild. All optional: an
  // environment without them shows "not configured" instead of a broken button.
  NEXUS_META_APP_ID: z.string().optional(),
  NEXUS_META_GRAPH_API_VERSION: z.string().default("v22.0"),
  NEXUS_META_CONFIG_ID_WA_CLOUD_API: z.string().optional(),
  NEXUS_META_CONFIG_ID_WA_COEXISTENCE: z.string().optional(),
  // Lane channels (CP-20): origin of the @auphere/embed iframe app.
});

export type Env = z.infer<typeof schema>;

let cached: Env | null = null;

export function env(): Env {
  if (cached) return cached;
  const parsed = schema.safeParse({
    ...process.env,
    // Real newlines in a PEM cannot travel through most env UIs; accept "\n".
    NEXUS_CONSOLE_JWT_PRIVATE_KEY: process.env.NEXUS_CONSOLE_JWT_PRIVATE_KEY?.replace(/\\n/g, "\n"),
  });
  if (!parsed.success) {
    const missing = parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
    throw new Error(`apps/console: invalid environment — ${missing}`);
  }
  cached = parsed.data;
  return cached;
}
