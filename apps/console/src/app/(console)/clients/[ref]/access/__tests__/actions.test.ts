import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { inviteClientMemberAction, reloadClientAccessAction, resendClientMemberAction, revokeClientMemberAction, setClientAccessAction } =
  await import("../actions");

const MEMBER = "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d";

/** Cada acción con una entrada válida y el método del backend que llama. */
const CASES = [
  { name: "reload", run: () => reloadClientAccessAction({ ref: "flor" }), method: "clientAccess" },
  {
    name: "set",
    run: () => setClientAccessAction({ ref: "flor", enabled: true, modules: ["panel", "reservas"], reservas: { mode: "services" } }),
    method: "setClientAccess",
  },
  { name: "invite", run: () => inviteClientMemberAction({ ref: "flor", email: "ana@negocio.test", name: "Ana" }), method: "inviteClientMember" },
  { name: "resend", run: () => resendClientMemberAction({ ref: "flor", member: MEMBER }), method: "resendClientMember" },
  { name: "revoke", run: () => revokeClientMemberAction({ ref: "flor", member: MEMBER }), method: "revokeClientMember" },
] as const;

/**
 * Spec 056 (requisitos 3.1, 3.2; D4) — la pestaña «Acceso» es de owner y admin
 * (`client_access:manage`). Los demás roles y la persona de un cliente reciben la
 * negativa de la consola antes de llamar a la API.
 */
describe("acciones del Acceso del cliente", () => {
  beforeEach(() => {
    for (const c of CASES) h.backend[c.method].mockClear();
    h.cacheModule.revalidatePath.mockClear();
  });

  it.each(["owner", "admin"] as const)("%s puede todo", async (role) => {
    h.setRole(role);
    for (const c of CASES) {
      const res = await c.run();
      expect(res.ok, c.name).toBe(true);
      expect(h.backend[c.method], c.name).toHaveBeenCalledTimes(1);
    }
    expect(h.backend.setClientAccess).toHaveBeenCalledWith("flor", { enabled: true, modules: ["panel", "reservas"], reservas: { mode: "services" } });
    expect(h.backend.inviteClientMember).toHaveBeenCalledWith("flor", { email: "ana@negocio.test", name: "Ana" });
    expect(h.backend.revokeClientMember).toHaveBeenCalledWith("flor", MEMBER);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/flor/access");
  });

  it.each(["builder", "analyst", "billing"] as const)("%s recibe la negativa y no llama a nadie", async (role) => {
    h.setRole(role);
    for (const c of CASES) {
      expect(await c.run(), c.name).toEqual(h.denied());
      expect(h.backend[c.method], c.name).not.toHaveBeenCalled();
    }
  });

  it("la persona de un cliente tampoco", async () => {
    h.setClient(["panel", "inbox", "usage"]);
    for (const c of CASES) {
      expect(await c.run(), c.name).toEqual(h.denied());
      expect(h.backend[c.method], c.name).not.toHaveBeenCalled();
    }
  });

  it("Agentes y Negocio no son módulos: ni se envían", async () => {
    h.setRole("owner");
    await expect(setClientAccessAction({ ref: "flor", enabled: true, modules: ["panel", "agents"] })).rejects.toThrow();
    await expect(setClientAccessAction({ ref: "flor", enabled: true, modules: ["business"] })).rejects.toThrow();
    expect(h.backend.setClientAccess).not.toHaveBeenCalled();
  });

  it("ningún cuerpo lleva el partner ni el tenant", async () => {
    h.setRole("owner");
    await expect(setClientAccessAction({ ref: "flor", enabled: false, modules: [], partner_id: "p" })).rejects.toThrow();
    await expect(inviteClientMemberAction({ ref: "flor", email: "a@b.test", tenant_id: "t" })).rejects.toThrow();
    await expect(resendClientMemberAction({ ref: "flor", member: "no-es-un-id" })).rejects.toThrow();
  });

  it("devuelve el código de la API para que la pantalla diga la frase", async () => {
    h.setRole("owner");
    h.fail("setClientAccess", 409, "", "live_reservations", { count: 2 });
    expect(await setClientAccessAction({ ref: "flor", enabled: true, modules: ["reservas"], reservas: { mode: "services" } })).toMatchObject({
      ok: false,
      status: 409,
      code: "live_reservations",
      info: { count: 2 },
    });
  });
});
