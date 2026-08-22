/**
 * Guardia del QA Playground — ``role`` del operador (ADR-034).
 *
 * Antes esto hacía un SELECT con Drizzle sobre ``auth.user`` para leer el
 * rol. Ya no hay Drizzle ni ``auth.user``: el rol viaja en la respuesta de
 * ``/admin/auth/session``, que es la misma llamada que ya resuelve la
 * sesión. Cero consultas extra.
 *
 * Lo que gatea, y por qué sigue existiendo:
 *
 *   - 401 si no hay sesión.
 *   - 403 si el rol no está en ``QA_ROLES`` (``admin`` / ``qa_operator``).
 *   - 403 si la cuenta está deshabilitada.
 *   - ``{ operatorId, role, email }`` en cualquier otro caso.
 *
 * ``require_qa_operator`` en el backend sólo comprueba el bearer y que
 * ``X-Operator-Id`` sea una cadena no vacía: sin esta guardia, cualquier
 * usuario del panel —incluido uno degradado a ``viewer``— llegaría al
 * Playground. El backend sigue siendo el que aplica RLS; el BFF es quien
 * decide qué operador se le anuncia.
 */
import "server-only";

import { QA_ROLES, type Role } from "./operator-auth";
import { getOperator } from "./session";

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
 * Se usa dentro de un route handler del BFF para gatear ``/api/qa/*``.
 * Lanza ``QAForbidden`` con el estado correcto; el llamante lo captura y
 * responde con ``NextResponse.json(...)``.
 */
export async function requireQAOperator(): Promise<QAAccess> {
  const operator = await getOperator();
  if (!operator) throw new QAForbidden("no-session", 401);
  // Una cuenta revocada conserva su fila y su rol; lo que pierde es el
  // derecho a operar. Sin esta línea seguiría entrando al Playground.
  if (operator.access !== "ok") throw new QAForbidden("wrong-role", 403, operator.role);
  if (!(QA_ROLES as readonly string[]).includes(operator.role)) {
    throw new QAForbidden("wrong-role", 403, operator.role);
  }
  return {
    operatorId: operator.id,
    email: operator.email,
    role: operator.role,
  };
}
