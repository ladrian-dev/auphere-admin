/**
 * Spec 079, requisito 1: what each role of the operator panel may do.
 *
 * The authority is the API (`apps/api/src/nexus_api/core/operator_permissions.py`).
 * This copy decides and renders in the panel; `lib/__tests__/permissions.test.ts`
 * reads the API file and fails on any drift — change both in the same commit.
 *
 * What each permission covers: `specs/079-panel-respeta-el-rol/inventario.md`.
 * Pure module (no `server-only`) so the shell, components and tests can use it.
 */
import type { Role } from "./operator-auth";

export const PERMISSIONS = {
  read: ["admin", "qa_operator", "viewer"],
  qa: ["admin", "qa_operator"],
  operate: ["admin", "qa_operator"],
  money: ["admin"],
  credentials: ["admin"],
  impersonate: ["admin"],
  people: ["admin"],
  delete: ["admin"],
  platform: ["admin"],
} as const satisfies Record<string, readonly Role[]>;

export type Permission = keyof typeof PERMISSIONS;

/**
 * `false` for a disabled account, an unknown role or an unknown permission:
 * the panel fails closed (spec 079, criterion 1.4).
 */
export function can(operator: { role: string; access: string }, permission: Permission): boolean {
  if (operator.access !== "ok") return false;
  const roles: readonly string[] = PERMISSIONS[permission] ?? [];
  return roles.includes(operator.role);
}
