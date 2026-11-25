/**
 * Spec 079, criterio 1.4: `/sin-acceso` usa la misma regla que la guarda. Una
 * cuenta activa con un rol que la matriz no conoce se queda aquí: si la página
 * la mandara a `/tenants`, la guarda la devolvería y no acabaría nunca.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

class Redirect extends Error {
  constructor(readonly to: string) {
    super(`redirect:${to}`);
  }
}

let current: unknown = null;

vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Redirect(to);
  },
}));
vi.mock("@/lib/session", () => ({ getOperator: async () => current }));
vi.mock("../sign-out-button", () => ({ SignOutButton: () => null }));

const { default: NoAccessPage } = await import("../page");

const operator = (access: "ok" | "disabled", role: string) => ({
  id: "op-1",
  email: "op@auphere.test",
  display_name: null,
  locale: "es",
  access,
  role,
});

async function outcome(): Promise<string> {
  try {
    await NoAccessPage();
    return "stays";
  } catch (error) {
    if (error instanceof Redirect) return error.message;
    throw error;
  }
}

beforeEach(() => {
  current = null;
});

describe("/sin-acceso (spec 078, 2.2; spec 079, 1.4)", () => {
  it("sin sesión, al login", async () => {
    expect(await outcome()).toBe("redirect:/login");
  });

  it("una cuenta deshabilitada se queda", async () => {
    current = operator("disabled", "admin");
    expect(await outcome()).toBe("stays");
  });

  it("una cuenta activa con un rol desconocido se queda, sin bucle", async () => {
    current = operator("ok", "owner");
    expect(await outcome()).toBe("stays");
  });

  it("una cuenta activa con un rol conocido vuelve al panel", async () => {
    current = operator("ok", "viewer");
    expect(await outcome()).toBe("redirect:/tenants");
  });
});
