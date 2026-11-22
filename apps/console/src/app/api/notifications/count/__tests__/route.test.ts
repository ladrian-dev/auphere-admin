/**
 * `GET /api/notifications/count` — el número de la campana (spec 071): avisos
 * sin leer más lo de «Ahora». Es una ruta y no una acción de servidor para que
 * una lectura en segundo plano no pase por la cola del router (spec 074).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  resolution: { kind: "anonymous" } as unknown,
  unread: vi.fn(),
  attention: vi.fn(),
}));
vi.mock("@/lib/principal", async () => ({
  can: (await import("@/lib/permissions")).can,
  resolvePrincipal: async () => state.resolution,
}));
vi.mock("@/lib/backend", async () => {
  class BackendError extends Error {
    constructor(
      public status: number,
      public url: string,
      public body: unknown,
    ) {
      super(`backend ${status}`);
    }
  }
  return { BackendError, backendFor: () => ({ unreadNotifications: state.unread, attention: state.attention }) };
});

const { GET } = await import("../route");
const { BackendError } = await import("@/lib/backend");

const partner = { kind: "ok", principal: { kind: "partner", role: "builder", modules: ["panel"] } };
const item = { scope: "partner", severity: "warning", code: "build_cap_warning", count: 1 };

describe("GET /api/notifications/count", () => {
  beforeEach(() => {
    state.resolution = partner;
    state.unread.mockReset().mockResolvedValue({ unread: 1 });
    state.attention.mockReset().mockResolvedValue({ items: [item, item], errors: [] });
  });

  it("suma los avisos sin leer y lo de «Ahora», sin caché", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ unread: 3 });
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("si «Ahora» falla, cuenta solo los avisos", async () => {
    state.attention.mockRejectedValue(new BackendError(502, "/console/attention", null));
    expect(await (await GET()).json()).toEqual({ unread: 1 });
  });

  it("si los avisos fallan, dice el estado y nada más", async () => {
    state.unread.mockRejectedValue(new BackendError(503, "/console/notifications/unread-count", { detail: "secreto" }));
    const res = await GET();
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ detail: "Count failed" });
  });

  it("sin sesión: 401; sin acceso: 403; y no pregunta a la API", async () => {
    state.resolution = { kind: "anonymous" };
    expect((await GET()).status).toBe(401);
    state.resolution = { kind: "suspended" };
    expect((await GET()).status).toBe(403);
    expect(state.unread).not.toHaveBeenCalled();
  });
});
