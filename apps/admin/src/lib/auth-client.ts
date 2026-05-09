"use client";

/**
 * Client-side Better Auth surface used by ``/login`` and the
 * ``<UserMenu />`` sidebar footer to call ``signIn`` / ``signOut`` /
 * read the current session inside Client Components.
 *
 * Server Components and Server Actions don't import this — they call
 * ``auth.api.getSession({ headers })`` directly via ``@/lib/auth``.
 */

import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL:
    typeof window !== "undefined"
      ? window.location.origin
      : process.env.NEXUS_ADMIN_ORIGIN ?? "http://localhost:3000",
});

export const { signIn, signOut, signUp, useSession, getSession } = authClient;
