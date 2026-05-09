/**
 * Session helpers used inside Server Components / Server Actions.
 *
 * The middleware does a cheap cookie check; this module does the real
 * verification (DB hit, expiry, etc.) and returns the typed session.
 */

import "server-only";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "./auth";

export async function getSession() {
  return auth.api.getSession({ headers: await headers() });
}

export async function requireSession() {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}
