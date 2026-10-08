import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Spec 030 (R2.4, R3.4): adónde va cada persona cuando pide lo que no es suyo.
 *
 * - Una persona de cliente que pide una página del partner va a su primer
 *   módulo, sin una pantalla que explique lo que no tiene (constitución §V).
 * - Una persona de cliente que pide un módulo que su cliente no tiene, igual.
 * - Un miembro del partner que pide una página lite vuelve a su Inicio.
 */
const redirect = vi.fn((to: string) => {
  throw new Error(`REDIRECT ${to}`);
});
vi.mock("next/navigation", () => ({ redirect }));

const session = vi.fn();
vi.mock("@/lib/session", () => ({ getSessionToken: async () => "tok" }));
vi.mock("@/lib/backend", () => ({ consoleService: { session } }));

const base = {
  user_id: "u",
  email: "x@y.test",
  display_name: "X",
  locale: "es",
  access: "ok" as const,
  membership_id: "m",
  partner_id: "p",
  partner_slug: "demo",
  partner_name: "Demo",
  partner_status: "active",
  console_enabled: true,
};
const partner = { ...base, role: "owner", permissions: ["partner:read"], kind: "partner", client_name: null, modules: [] };
const client = (modules: string[]) => ({
  ...base,
  role: "client",
  permissions: [],
  kind: "client",
  client_name: "Flor y Encanto",
  modules,
});

async function load() {
  vi.resetModules();
  return import("@/lib/principal");
}

beforeEach(() => {
  redirect.mockClear();
  session.mockReset();
});

describe("requirePartnerPrincipal", () => {
  it("returns a partner member", async () => {
    session.mockResolvedValue(partner);
    const { requirePartnerPrincipal } = await load();
    expect((await requirePartnerPrincipal()).kind).toBe("partner");
  });

  it.each([
    [["panel", "inbox"], "/"],
    [["inbox", "usage"], "/inbox"],
    [["usage"], "/usage"],
  ])("sends a client with %j to %s", async (modules, to) => {
    session.mockResolvedValue(client(modules));
    const { requirePartnerPrincipal } = await load();
    await expect(requirePartnerPrincipal("/clients")).rejects.toThrow(`REDIRECT ${to}`);
  });
});

describe("requireClientPrincipal", () => {
  it("returns a client with the module", async () => {
    session.mockResolvedValue(client(["panel", "inbox"]));
    const { requireClientPrincipal } = await load();
    const p = await requireClientPrincipal("inbox");
    expect(p.kind === "client" && p.clientName).toBe("Flor y Encanto");
  });

  it("sends a client without the module to its first one", async () => {
    session.mockResolvedValue(client(["usage"]));
    const { requireClientPrincipal } = await load();
    await expect(requireClientPrincipal("inbox")).rejects.toThrow("REDIRECT /usage");
  });

  it("sends a partner member home", async () => {
    session.mockResolvedValue(partner);
    const { requireClientPrincipal } = await load();
    await expect(requireClientPrincipal("inbox")).rejects.toThrow("REDIRECT /");
  });
});
