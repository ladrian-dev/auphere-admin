/**
 * The role → permission map, mirrored from ``core/console_auth.py``. The
 * API is the authority (``GET /console/me`` returns the resolved list);
 * this copy only decides what to RENDER before the first backend call.
 * A drift is caught by ``lib/__tests__/permissions.test.ts``.
 *
 * Pure module (no server-only) so nav and tests can import it.
 */
export type Role = "owner" | "admin" | "builder" | "analyst" | "billing";

export const PERMISSIONS = {
  "partner:read": ["owner", "admin", "builder", "analyst", "billing"],
  "clients:read": ["owner", "admin", "builder", "analyst"],
  "clients:write": ["owner", "admin", "builder"],
  "clients:delete": ["owner", "admin"],
  "agents:read": ["owner", "admin", "builder", "analyst"],
  "agents:write": ["owner", "admin", "builder"],
  "channels:read": ["owner", "admin", "builder", "analyst"],
  "channels:write": ["owner", "admin", "builder"],
  "conversations:read": ["owner", "admin", "builder", "analyst"],
  "usage:read": ["owner", "admin", "builder", "analyst", "billing"],
  "audit:read": ["owner", "admin", "analyst"],
  "team:read": ["owner", "admin", "builder", "analyst", "billing"],
  "team:manage": ["owner", "admin"],
  "keys:read": ["owner", "admin", "builder"],
  "keys:manage": ["owner", "admin"],
  "billing:read": ["owner", "billing"],
  "billing:manage": ["owner", "billing"],
  "playground:run": ["owner", "admin", "builder"],
  "usage:manage": ["owner", "admin"],
  "usage:write": ["owner", "admin"],
  "knowledge:read": ["owner", "admin", "builder", "analyst"],
  "knowledge:write": ["owner", "admin", "builder"],
  "playbook:read": ["owner", "admin", "builder", "analyst"],
  "playbook:write": ["owner", "admin"],
  // The console Companion (CO-01). Same three roles as `playground:run`:
  // it spends the partner's LLM budget and, from CO-04, it writes — through
  // the very same `/console/*` routers, so an analyst still gets the
  // router's 403 for anything it may not do.
  "companion:use": ["owner", "admin", "builder"],
} as const satisfies Record<string, readonly Role[]>;

export type Permission = keyof typeof PERMISSIONS;

export function can(role: Role, permission: Permission): boolean {
  return (PERMISSIONS[permission] as readonly Role[]).includes(role);
}
