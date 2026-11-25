/**
 * Spec 078, requisito 2.1: `requireOperator()` solo devuelve operadores que
 * pueden operar. Sin sesión, al login; con la cuenta deshabilitada, a
 * `/sin-acceso`.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

class Redirect extends Error {
  constructor(readonly to: string) {
    super(`redirect:${to}`);
  }
}

let cookie: string | undefined;
let resolved: unknown = null;

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => (cookie ? { value: cookie } : undefined) }),
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Redirect(to);
  },
}));
vi.mock("../impersonate", () => ({ clearImpersonateCookie: async () => undefined }));
vi.mock("../operator-auth", () => ({
  resolveSession: async () => resolved,
  login: vi.fn(),
  endSession: vi.fn(),
}));

const { requireOperator } = await import("../session");

const operator = (access: "ok" | "disabled") => ({
  id: "op-1",
  email: "op@auphere.test",
  display_name: null,
  locale: "es",
  access,
  role: "admin" as const,
});

async function outcome(): Promise<string> {
  try {
    const op = await requireOperator();
    return `operator:${op.access}`;
  } catch (error) {
    if (error instanceof Redirect) return error.message;
    throw error;
  }
}

beforeEach(() => {
  cookie = "token";
  resolved = null;
});

describe("requireOperator (spec 078, requisito 2.1)", () => {
  it("sin cookie, al login", async () => {
    cookie = undefined;
    expect(await outcome()).toBe("redirect:/login");
  });

  it("con una sesión que la API no reconoce, al login", async () => {
    resolved = null;
    expect(await outcome()).toBe("redirect:/login");
  });

  it("con la cuenta deshabilitada, a /sin-acceso y sin devolver el operador", async () => {
    resolved = operator("disabled");
    expect(await outcome()).toBe("redirect:/sin-acceso");
  });

  it("con la cuenta activa, devuelve el operador", async () => {
    resolved = operator("ok");
    expect(await outcome()).toBe("operator:ok");
  });
});
