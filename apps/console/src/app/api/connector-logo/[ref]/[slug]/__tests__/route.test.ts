/**
 * Spec 061 (1.8) — `GET /api/connector-logo/{ref}/{slug}` con un logotipo que servimos
 * nosotros. El de Quédate vive en `public/connector-logos/quedate.png`: la ruta manda
 * al navegador allí, a nuestro propio origen, sin pedir nada fuera. Cualquier otra
 * cosa que no sea https no se sigue.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ logo: null as string | null, fetch: vi.fn() }));
vi.mock("@/lib/principal", () => ({ resolvePrincipal: async () => ({ kind: "ok", principal: { kind: "partner" } }) }));
vi.mock("@/lib/backend", () => ({
  backendFor: () => ({ listConnectors: async () => [{ slug: "quedate", logo_url: state.logo }] }),
}));

const { GET } = await import("../route");

const call = () =>
  GET(new Request("http://console.test/api/connector-logo/flor/quedate"), { params: Promise.resolve({ ref: "flor", slug: "quedate" }) });

describe("GET /api/connector-logo · los logotipos que servimos nosotros", () => {
  beforeEach(() => {
    state.fetch.mockReset();
    vi.stubGlobal("fetch", state.fetch);
  });

  it("una ruta /connector-logos/ lleva a nuestro origen, sin pedir nada fuera", async () => {
    state.logo = "/connector-logos/quedate.png";
    const res = await call();
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("/connector-logos/quedate.png");
    expect(state.fetch).not.toHaveBeenCalled();
  });

  it.each(["/api/session", "//evil.example/x.png", "/connector-logos/../api/x.png", "http://insecure.example/x.png"])(
    "%s no se sigue",
    async (logo) => {
      state.logo = logo;
      const res = await call();
      expect(res.status).toBe(404);
      expect(state.fetch).not.toHaveBeenCalled();
    },
  );
});
