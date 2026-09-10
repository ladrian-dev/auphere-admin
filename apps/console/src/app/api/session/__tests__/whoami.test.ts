/**
 * Requisitos 2.4 y 11.1 (spec 002) — `whoami` dice quién está dentro, y nada más.
 */
import { describe, expect, it, vi } from "vitest";

const resolvePrincipal = vi.fn();
vi.mock("@/lib/principal", () => ({ resolvePrincipal: () => resolvePrincipal() }));

import { GET } from "../whoami/route";

describe("GET /api/session/whoami", () => {
  it("con sesión y pertenencia: user_id y partner_slug, y nada más", async () => {
    resolvePrincipal.mockResolvedValue({
      kind: "ok",
      principal: { userId: "luis", partnerSlug: "nexus-retail", email: "luis@x.com", role: "owner", name: "Luis" },
    });
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ user_id: "luis", partner_slug: "nexus-retail" });
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
