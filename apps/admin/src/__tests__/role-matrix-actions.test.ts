/**
 * Spec 079, criterios 1.2, 2.1 y 2.2 (CE-001): la matriz aplicada a acciones de
 * verdad. Con la sesión de cada rol se invoca una acción por permiso; el rol sin
 * el permiso no hace ninguna llamada a la API y vuelve a la misma página con el
 * aviso, y el rol que lo tiene sí llega a la API.
 *
 * Solo se simulan los bordes: la sesión, las cabeceras, la navegación y `fetch`.
 * La guarda, las acciones y el cliente de la API son los de verdad.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

class Redirect extends Error {
  constructor(readonly to: string) {
    super(`redirect:${to}`);
  }
}

let role = "admin";

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => ({ value: "token" }), set: vi.fn(), delete: vi.fn() }),
  headers: async () => ({
    get: (name: string) =>
      ({ host: "admin.auphere.test", referer: "https://admin.auphere.test/partners/p-1" })[name.toLowerCase()] ?? null,
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Redirect(to);
  },
  notFound: () => {
    throw new Error("not-found");
  },
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn(), revalidateTag: vi.fn() }));
vi.mock("@/lib/operator-auth", () => ({
  resolveSession: async () => ({
    id: "00000000-0000-4000-8000-000000000001",
    email: "op@auphere.test",
    display_name: null,
    locale: "es",
    access: "ok",
    role,
  }),
  login: vi.fn(),
  endSession: vi.fn(),
}));
vi.mock("@/lib/impersonate", () => ({
  clearImpersonateCookie: async () => undefined,
  setImpersonateCookie: async () => undefined,
}));

const fetchSpy = vi.fn(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
vi.stubGlobal("fetch", fetchSpy);
vi.spyOn(console, "warn").mockImplementation(() => undefined);

const ID = "00000000-0000-4000-8000-0000000000aa";

const tenantsNew = await import("@/app/(dashboard)/tenants/new/actions");
const agent = await import("@/app/(dashboard)/tenants/[id]/agent/actions");
const partners = await import("@/app/(dashboard)/partners/actions");
const invitation = await import("@/app/(dashboard)/partners/_invitation/actions");
const tenants = await import("@/app/(dashboard)/tenants/actions");
const models = await import("@/app/(dashboard)/models/actions");

/** One action per permission of the matrix (inventario.md). */
const CASES = [
  ["read", () => tenantsNew.checkSlugAction("demo")],
  ["qa", () => agent.testAgentTurnAction(ID, { message: "hola" } as never)],
  ["operate", () => agent.stageAgentConfigAction(ID, { system_prompt: "x" } as never)],
  ["money", () => partners.rechargePartnerWallet(ID, 1000, "idem-1")],
  ["credentials", () => partners.createPartnerKeyAction(ID, { name: "k" } as never)],
  ["impersonate", () => partners.startImpersonationAction(ID, "soporte", 600)],
  ["people", () => invitation.inviteOwnerAction(ID, "owner@negocio.test")],
  ["delete", () => tenants.deleteTenantAction(ID)],
  ["platform", () => models.activateAction(ID, "alta")],
] as const;

const GRANTED: Record<string, readonly string[]> = {
  admin: ["read", "qa", "operate", "money", "credentials", "impersonate", "people", "delete", "platform"],
  qa_operator: ["read", "qa", "operate"],
  viewer: ["read"],
};

async function run(invoke: () => Promise<unknown>): Promise<"denied" | "reached"> {
  try {
    await invoke();
  } catch (error) {
    if (error instanceof Redirect && error.to.includes("sin-permiso=1")) return "denied";
    throw error;
  }
  return "reached";
}

beforeEach(() => {
  fetchSpy.mockClear();
});

describe.each(Object.keys(GRANTED))("rol %s (spec 079, 1.2 y 2.1)", (current) => {
  it.each(CASES)("%s", async (permission, invoke) => {
    role = current;
    const outcome = await run(invoke);
    if (GRANTED[current]!.includes(permission)) {
      expect(outcome).toBe("reached");
      expect(fetchSpy).toHaveBeenCalled();
    } else {
      expect(outcome).toBe("denied");
      expect(fetchSpy).not.toHaveBeenCalled();
    }
  });
});
