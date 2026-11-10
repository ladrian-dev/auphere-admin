/**
 * Spec 047 (R47.2) — `GET /api/search?q=`: el puente del navegador a
 * `GET /console/search` para la paleta ⌘K del marco nuevo.
 *
 * La forma de seguridad es la de siempre (constitución, consola sin
 * credenciales): el principal se resuelve en el servidor, solo una persona de
 * partner busca, y la llamada sale con un token de 60 s recién emitido. Qué
 * acciones puede hacer la persona lo decide la API; aquí no se filtra nada.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ resolution: { kind: "anonymous" } as unknown, call: vi.fn() }));
vi.mock("@/lib/principal", () => ({ resolvePrincipal: async () => state.resolution }));
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
  return {
    BackendError,
    callFor: () => state.call,
    q: (p: Record<string, string>) => `?${new URLSearchParams(p).toString()}`,
  };
});

const { GET } = await import("../route");

const partner = { kind: "ok", principal: { kind: "partner", role: "builder", modules: ["panel", "clients"] } };
const RESULT = { clients: [], agents: [{ agent_id: "a-1", name: "Recepción", client_ref: "flor", client_name: "Flor y Encanto" }], screens: [], actions: [] };

describe("GET /api/search", () => {
  beforeEach(() => {
    state.call.mockReset().mockResolvedValue(RESULT);
    state.resolution = partner;
  });

  it("una persona de partner busca y recibe lo que dice la API, sin caché", async () => {
    const res = await GET(new Request("http://console.test/api/search?q=Recep"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(RESULT);
    expect(state.call).toHaveBeenCalledWith("/console/search?q=Recep");
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("sin texto también pregunta (la API decide qué pantallas y acciones ofrece)", async () => {
    await GET(new Request("http://console.test/api/search"));
    expect(state.call).toHaveBeenCalledWith("/console/search?q=");
  });

  it("sin sesión: 401", async () => {
    state.resolution = { kind: "anonymous" };
    expect((await GET(new Request("http://console.test/api/search?q=a"))).status).toBe(401);
    expect(state.call).not.toHaveBeenCalled();
  });

  it("una persona de cliente no usa la búsqueda del partner: 403", async () => {
    state.resolution = { kind: "ok", principal: { kind: "client", role: "client", modules: ["panel"] } };
    expect((await GET(new Request("http://console.test/api/search?q=a"))).status).toBe(403);
    expect(state.call).not.toHaveBeenCalled();
  });

  it("un texto de más de 120 caracteres no sale hacia la API: 422", async () => {
    const res = await GET(new Request(`http://console.test/api/search?q=${"x".repeat(121)}`));
    expect(res.status).toBe(422);
    expect(state.call).not.toHaveBeenCalled();
  });

  it("un error de la API se reenvía con su estado y sin detalles internos", async () => {
    const { BackendError } = await import("@/lib/backend");
    state.call.mockRejectedValue(new (BackendError as unknown as new (s: number, u: string, b: unknown) => Error)(503, "http://api/console/search", { detail: "db down" }));
    const res = await GET(new Request("http://console.test/api/search?q=a"));
    expect(res.status).toBe(503);
    expect(JSON.stringify(await res.json())).not.toMatch(/db down|http:\/\/api/);
  });
});
