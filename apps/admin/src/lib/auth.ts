/**
 * Better Auth — Auphere internal-only configuration.
 *
 * Phase 1 = email + password, single org "Auphere", invitation later.
 * Sessions sit in the dedicated ``auth`` Postgres schema (see
 * ``src/db/schema.ts``). The session cookie is the only thing the
 * server actions use; the FastAPI backend never sees Better Auth — it
 * only validates the static admin Bearer token forwarded by server
 * actions / server components.
 *
 * We do NOT enable email verification flows in Phase 1 because the
 * single user (Lee) is bootstrapped via the seed-admin script.
 */

import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";

import { db } from "@/db/client";
import { account, session, user, verification } from "@/db/schema";

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
    schema: { user, session, account, verification },
  }),
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
    requireEmailVerification: false,
    minPasswordLength: 12,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7, // 7 days
    updateAge: 60 * 60 * 24, // refresh once a day
    cookieCache: { enabled: true, maxAge: 60 * 5 },
  },
  advanced: {
    cookiePrefix: "nexus",
    defaultCookieAttributes: {
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    },
  },
  trustedOrigins: [
    process.env.NEXUS_ADMIN_ORIGIN ?? "http://localhost:3000",
  ],
});

export type Session = typeof auth.$Infer.Session;
