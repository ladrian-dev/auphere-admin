/**
 * Spec 079, criterio 2.4: archivar es borrar (constitución §IV, «borrar no
 * existe: se archiva») y no puede compartir acción con pausar y reanudar, que
 * son operación del día a día. Cada una pide su propio permiso.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const asked: string[] = [];
vi.mock("@/lib/session", () => ({
  requireOperator: async (permission: string) => {
    asked.push(permission);
    return { id: "op-1", role: "admin", access: "ok" };
  },
}));

const updateTenant = vi.fn(async (_id: string, body: { status: string }) => ({ status: body.status }));
let currentStatus = "paused";
vi.mock("@/lib/backend", async (orig) => ({
  ...(await orig<typeof import("@/lib/backend")>()),
  backend: {
    updateTenant: (id: string, body: { status: string }) => updateTenant(id, body),
    getTenant: async () => ({ status: currentStatus }),
  },
}));

const actions = await import("../actions");

beforeEach(() => {
  asked.length = 0;
  currentStatus = "paused";
  updateTenant.mockClear();
});

describe("estado del cliente (spec 079, 2.4)", () => {
  it("no queda una acción que pause y archive a la vez", () => {
    expect("setTenantStatusAction" in actions).toBe(false);
  });

  it("pausar y reanudar piden operate", async () => {
    await actions.setTenantPausedAction("t-1", "paused");
    await actions.setTenantPausedAction("t-1", "active");
    expect(asked).toEqual(["operate", "operate"]);
    expect(updateTenant.mock.calls.map((c) => c[1].status)).toEqual(["paused", "active"]);
  });

  it("pausar no acepta archivar, aunque llegue desde el navegador", async () => {
    const res = await actions.setTenantPausedAction("t-1", "archived" as never);
    expect(res.ok).toBe(false);
    expect(updateTenant).not.toHaveBeenCalled();
  });

  it("reactivar un cliente archivado deshace un borrado: pide también delete", async () => {
    currentStatus = "archived";
    await actions.setTenantPausedAction("t-1", "active");
    expect(asked).toEqual(["operate", "delete"]);
  });

  it("archivar pide delete", async () => {
    await actions.archiveTenantAction("t-1");
    expect(asked).toEqual(["delete"]);
    expect(updateTenant).toHaveBeenCalledWith("t-1", { status: "archived" });
  });
});
