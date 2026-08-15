import "server-only";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "./auth";

/** Real verification (DB hit). The middleware only checks cookie presence. */
export async function getSession() {
  return auth.api.getSession({ headers: await headers() });
}

export async function requireSession(from?: string) {
  const session = await getSession();
  if (!session) redirect(from ? `/login?from=${encodeURIComponent(from)}` : "/login");
  return session;
}
