import { z } from "zod";

/**
 * Validated server environment (no ``server-only`` marker on purpose: the
 * seed script runs it under tsx). Read once, fail loudly at boot: a console
 * that starts without its signing key would produce 401s that look like a
 * backend problem. There is deliberately NO static admin credential here —
 * ``scripts/check-no-admin-token.mjs`` (CI) fails if the admin token name
 * ever appears in this app.
 */
const schema = z.object({
  NEXUS_BACKEND_URL: z.string().url().default("http://localhost:8000"),
  NEXUS_CONSOLE_ORIGIN: z.string().url().default("http://localhost:3110"),
  NEXUS_CONSOLE_DATABASE_URL: z.string().min(1),
  NEXUS_CONSOLE_JWT_PRIVATE_KEY: z.string().min(1),
  NEXUS_CONSOLE_JWT_ISSUER: z.string().default("nexus-console"),
  NEXUS_CONSOLE_JWT_AUDIENCE: z.string().default("nexus-api"),
  BETTER_AUTH_SECRET: z.string().min(32),
  BETTER_AUTH_URL: z.string().url().optional(),
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
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
