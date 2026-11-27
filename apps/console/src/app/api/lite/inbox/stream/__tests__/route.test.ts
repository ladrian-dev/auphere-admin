/**
 * Spec 082: la línea en vivo de la consola (requisitos 1.11 y 3.12).
 *
 * Desde la 082 la abre también quien tiene Reservas sin Bandeja, y la ruta
 * declara su duración máxima para que la plataforma la corte limpia y
 * `EventSource` reconecte con un token nuevo.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ resolution: { kind: "anonymous" } as unknown, fetch: vi.fn() }));
vi.mock("@/lib/principal", () => ({ resolvePrincipal: async () => state.resolution }));
vi.mock("@/lib/backend", () => ({ tokenFor: async () => "t" }));
vi.mock("@/lib/env", () => ({ env: () => ({ NEXUS_BACKEND_URL: "http://api.test" }) }));

const route = await import("../route");

const client = (modules: string[]) => ({ kind: "ok", principal: { kind: "client", modules } });
const req = () => new Request("http://console.test/api/lite/inbox/stream");

describe("GET /api/lite/inbox/stream", () => {
  beforeEach(() => {
    state.fetch.mockReset().mockResolvedValue(new Response("event: ready\ndata: {}\n\n", { status: 200 }));
    vi.stubGlobal("fetch", state.fetch);
  });

  it("declara su duración máxima (3.12)", () => {
    expect(route.maxDuration).toBe(300);
  });

  it("la abre quien tiene Reservas sin Bandeja (1.11)", async () => {
    state.resolution = client(["panel", "reservas"]);
    const res = await route.GET(req());
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/event-stream");
    expect(state.fetch).toHaveBeenCalledWith("http://api.test/console/lite/inbox/stream", expect.anything());
  });

  it("y quien tiene la Bandeja", async () => {
    state.resolution = client(["inbox"]);
    expect((await route.GET(req())).status).toBe(200);
  });

  it("sin Bandeja ni Reservas, 403 y sin llamar a la API", async () => {
    state.resolution = client(["panel"]);
    expect((await route.GET(req())).status).toBe(403);
    expect(state.fetch).not.toHaveBeenCalled();
  });

  it("un partner no la abre", async () => {
    state.resolution = { kind: "ok", principal: { kind: "partner", modules: ["panel"] } };
    expect((await route.GET(req())).status).toBe(403);
  });
});
