/**
 * Harness for testing Server Actions (spec 016, R8).
 *
 * A server action does three things: resolve the principal, check the
 * role, call the backend. The harness fakes the first and the third so a
 * test can assert the second — the console's own "you cannot" instead of
 * the API's 403 — and what the backend was asked to do.
 *
 * Usage (the three `vi.mock` calls must be in the test file; Vitest hoists
 * them above the imports, and `vi.hoisted` runs before them):
 *
 *   const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
 *   vi.mock("@/lib/principal", () => h.principalModule);
 *   vi.mock("@/lib/backend", () => h.backendModule);
 *   vi.mock("next/cache", () => h.cacheModule);
 *   const { saveAllocationAction } = await import("../actions");
 *
 *   h.setRole("analyst");
 *   expect(await saveAllocationAction({ client_ref: "a", cap: 1 })).toEqual(h.denied());
 *   expect(h.backend.setAllocation).not.toHaveBeenCalled();
 */
import { vi } from "vitest";

import { PERMISSIONS, can, type Role } from "@/lib/permissions";

class FakeBackendError extends Error {
  status: number;
  detail: string;
  code: string | null;
  info: Record<string, unknown> | undefined;
  constructor(status: number, detail = "", code: string | null = null, info?: Record<string, unknown>) {
    super(detail || `backend ${status}`);
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.info = info;
  }
}

export type BackendFns = Record<string, ReturnType<typeof vi.fn>>;

export function actionHarness(initialRole: Role = "owner") {
  const state = { role: initialRole };
  const backend: BackendFns = {};

  const principal = () => ({
    userId: "u-1",
    email: "owner@demo.test",
    name: "Owner Demo",
    locale: "es" as const,
    membershipId: "m-1",
    partnerId: "p-1",
    partnerSlug: "demo",
    partnerName: "Demo",
    role: state.role,
    consoleEnabled: true,
  });

  // Every backend method exists and resolves to `{}` until a test says
  // otherwise with `h.backend.method.mockResolvedValue(...)`.
  const backendProxy = new Proxy({} as Record<string, unknown>, {
    get(_target, name) {
      const key = String(name);
      if (key === "then") return undefined;
      return (backend[key] ??= vi.fn(async () => ({})));
    },
  });

  return {
    state,
    backend,
    setRole(role: Role) {
      state.role = role;
    },
    /** The exact shape every action returns when the role cannot do it. */
    denied() {
      return { ok: false, status: 403, message: "forbidden" };
    },
    /** Make the next backend call fail the way `run()` would see it. */
    fail(method: string, status: number, detail = "", code: string | null = null) {
      (backend[method] ??= vi.fn()).mockRejectedValueOnce(new FakeBackendError(status, detail, code));
    },
    principalModule: {
      requirePrincipal: vi.fn(async () => principal()),
      resolvePrincipal: vi.fn(async () => ({ kind: "ok", principal: principal() })),
      can,
      PERMISSIONS,
    },
    backendModule: {
      backendFor: () => backendProxy,
      BackendError: FakeBackendError,
    },
    cacheModule: {
      revalidatePath: vi.fn(),
      revalidateTag: vi.fn(),
    },
  };
}

export type ActionHarness = ReturnType<typeof actionHarness>;
