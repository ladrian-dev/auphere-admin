/**
 * QA access guard — Better Auth ``user.role`` validation for ``/qa/*``.
 *
 * Resolves the current session, loads the user's ``role`` from the
 * ``auth.user`` table, and gates the QA Playground BFF proxies:
 *
 *   - 401 if no session.
 *   - 403 if the user exists but the role isn't in ``QA_ROLES``
 *     (``admin`` / ``qa_operator``).
 *   - returns ``{ operatorId, role, email }`` otherwise.
 *
 * Why a separate role check (vs trusting the Bearer + ``X-Operator-Id``
 * the backend accepts):
 *
 *   - The backend's ``require_qa_operator`` dependency only verifies
 *     the Bearer + that the header is a non-empty opaque string. Any
 *     authenticated admin-panel user — even one whose role is later
 *     downgraded to ``viewer`` — could otherwise reach the Playground.
 *   - This guard runs at the BFF layer, so the operator id forwarded
 *     to the backend is provably a user with the right role at the
 *     time of the request. The backend stays a thin RLS enforcer.
 *
 * Block G (eventual full Better Auth integration) will move this
 * validation into the FastAPI dependency itself. Until then, the BFF
 * is the gate.
 */
import "server-only";

import { eq } from "drizzle-orm";

import { db, schema } from "@/db/client";
import { QA_ROLES, type Role } from "@/db/schema";

import { getSession } from "./session";

export type QAAccess = {
  operatorId: string;
  email: string;
  role: Role;
};

export class QAForbidden extends Error {
  constructor(
    public readonly reason: "no-session" | "no-user" | "wrong-role",
    public readonly status: number,
    public readonly role?: string,
  ) {
    super(`QAForbidden: ${reason}${role ? ` (role=${role})` : ""}`);
  }
}

/**
 * Use inside a BFF route handler to gate ``/api/qa/*``. Throws
 * ``QAForbidden`` with the right HTTP status when the caller isn't
 * allowed. Callers catch it and return ``NextResponse.json(...)``.
 *
 * Cheap: one indexed SELECT on ``auth.user`` per request. Better Auth
 * already hits the DB to resolve the session, so we're paying one
 * extra round-trip — negligible vs the LLM cost of any QA turn.
 */
export async function requireQAOperator(): Promise<QAAccess> {
  const session = await getSession();
  if (!session) throw new QAForbidden("no-session", 401);

  const row = await db
    .select({ role: schema.user.role, email: schema.user.email })
    .from(schema.user)
    .where(eq(schema.user.id, session.user.id))
    .limit(1);
  if (row.length === 0) {
    throw new QAForbidden("no-user", 401);
  }
  const role = row[0].role as Role;
  if (!(QA_ROLES as readonly string[]).includes(role)) {
    throw new QAForbidden("wrong-role", 403, role);
  }
  return {
    operatorId: session.user.id,
    email: row[0].email,
    role,
  };
}
