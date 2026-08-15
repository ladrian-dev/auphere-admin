/**
 * Better Auth — partner console configuration.
 *
 * Email + password. Sign-up is NOT public: accounts are created only while
 * accepting an invitation (``app/(auth)/invite/[token]``), server-side,
 * after the invitation resolved. The public ``/api/auth/sign-up/*`` route
 * is refused in ``app/api/auth/[...all]/route.ts``.
 *
 * Cookies: ``__Host-`` prefix in production (secure, path=/, no domain),
 * HttpOnly, SameSite=Lax — the browser only ever holds this session; it
 * never sees a backend token (patrón BFF, CP-03).
 */

import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/next-js";

import { db } from "@/db/client";
import { account, session, user, verification } from "@/db/schema";
import { env } from "@/lib/env";

const isProd = process.env.NODE_ENV === "production";

export const auth = betterAuth({
  baseURL: env().BETTER_AUTH_URL ?? env().NEXUS_CONSOLE_ORIGIN,
  secret: env().BETTER_AUTH_SECRET,
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
  user: {
    additionalFields: {
      locale: { type: "string", required: false, defaultValue: "es", input: true },
    },
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7,
    updateAge: 60 * 60 * 24,
    cookieCache: { enabled: true, maxAge: 60 * 5 },
  },
  rateLimit: { enabled: true, window: 60, max: 30 },
  advanced: {
    cookiePrefix: "nexus-console",
    useSecureCookies: isProd,
    defaultCookieAttributes: { sameSite: "lax", secure: isProd, httpOnly: true, path: "/" },
  },
  trustedOrigins: [env().NEXUS_CONSOLE_ORIGIN],
  // Lets Server Actions (invitation acceptance) set the session cookie.
  // Must be the last plugin.
  plugins: [nextCookies()],
});

export type Session = typeof auth.$Infer.Session;
