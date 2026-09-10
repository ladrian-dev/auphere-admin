/**
 * Requisitos 2.4 y 11.1 (spec 002) — `whoami` dice quién está dentro, y nada más.
 *
 * La spec 003 le añade **una** clave: `permissions`, la lista ya resuelta. La
 * pantalla de operar tiene que saber si puede usar teammates sin deducirlo de
 * un rol —deducirlo sería una segunda copia del mapa de permisos—, y sigue sin
 * salir el rol, el correo ni el nombre.
 */
import { describe, expect, it, vi } from "vitest";

const resolvePrincipal = vi.fn();
vi.mock("@/lib/principal", () => ({ resolvePrincipal: () => resolvePrincipal() }));

import { GET } from "../whoami/route";

describe("GET /api/session/whoami", () => {
  it("con sesión y pertenencia: user_id, partner_slug, locale y permisos, y nada más", async () => {
    resolvePrincipal.mockResolvedValue({
      kind: "ok",
      principal: { userId: "luis", partnerSlug: "nexus-retail", locale: "es", email: "luis@x.com", role: "owner", name: "Luis" },
    });
    const res = await GET();
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["locale", "partner_slug", "permissions", "user_id"]);
    expect(body).toMatchObject({ user_id: "luis", partner_slug: "nexus-retail", locale: "es" });
    // Los permisos del rol, resueltos; ni el rol, ni el correo, ni el nombre.
    expect(body.permissions).toContain("teammates:use");
    expect(JSON.stringify(body)).not.toMatch(/luis@x\.com|owner|"Luis"/);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("sin sesión: 401", async () => {
    resolvePrincipal.mockResolvedValue({ kind: "anonymous" });
    const res = await GET();
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ code: "anonymous" });
  });

  it.each(["no-membership", "suspended", "disabled"])("con sesión pero %s: 403 no_membership", async (kind) => {
    resolvePrincipal.mockResolvedValue({ kind, email: "x@y.z" });
    const res = await GET();
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ code: "no_membership" });
  });
});
