/**
 * Spec 078 (requisito 2.1) y spec 079 (requisitos 1.4, 2.1–2.7): la guarda del
 * panel solo devuelve operadores que pueden operar **y** tienen el permiso que
 * pide quien la llama. Hay una variante por superficie (contrato
 * `specs/079-panel-respeta-el-rol/contracts/permisos-del-panel.md`).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

class Redirect extends Error {
  constructor(readonly to: string) {
    super(`redirect:${to}`);
  }
}
class NotFound extends Error {
  constructor() {
    super("not-found");
  }
}

let cookie: string | undefined;
let resolved: unknown = null;
let requestHeaders: Record<string, string> = {};
const revalidated: Array<[string, string | undefined]> = [];

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => (cookie ? { value: cookie } : undefined) }),
  headers: async () => ({ get: (name: string) => requestHeaders[name.toLowerCase()] ?? null }),
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Redirect(to);
  },
  notFound: () => {
    throw new NotFound();
  },
}));
vi.mock("next/cache", () => ({
  revalidatePath: (path: string, type?: string) => {
    revalidated.push([path, type]);
  },
}));
vi.mock("../impersonate", () => ({ clearImpersonateCookie: async () => undefined }));
vi.mock("../operator-auth", () => ({
  resolveSession: async () => resolved,
  login: vi.fn(),
  endSession: vi.fn(),
}));

const { requireOperator, requirePageOperator, routeOperator } = await import("../session");

const operator = (access: "ok" | "disabled", role = "admin") => ({
  id: "op-1",
  email: "op@auphere.test",
  display_name: null,
  locale: "es",
  access,
  role,
});

async function outcome(run: () => Promise<{ access: string }>): Promise<string> {
  try {
    const op = await run();
    return `operator:${op.access}`;
  } catch (error) {
    if (error instanceof Redirect || error instanceof NotFound) return error.message;
    throw error;
  }
}

const action = (permission: Parameters<typeof requireOperator>[0]) => () => requireOperator(permission);
const page = (permission: Parameters<typeof requirePageOperator>[0]) => () => requirePageOperator(permission);

let warn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  cookie = "token";
  resolved = null;
  requestHeaders = { host: "admin.auphere.test", referer: "https://admin.auphere.test/partners/p-1?tab=wallet" };
  revalidated.length = 0;
  warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  warn.mockClear();
});

describe.each([
  ["requireOperator", action],
  ["requirePageOperator", page],
] as const)("%s: sesión y cuenta (078, 2.1; 079, 1.4)", (_name, variant) => {
  it("sin cookie, al login", async () => {
    cookie = undefined;
    expect(await outcome(variant("read"))).toBe("redirect:/login");
  });

  it("con una sesión que la API no reconoce, al login", async () => {
    expect(await outcome(variant("read"))).toBe("redirect:/login");
  });

  it("con la cuenta deshabilitada, a /sin-acceso", async () => {
    resolved = operator("disabled");
    expect(await outcome(variant("read"))).toBe("redirect:/sin-acceso");
  });

  it("con un rol que la matriz no conoce, a /sin-acceso", async () => {
    resolved = operator("ok", "owner");
    expect(await outcome(variant("read"))).toBe("redirect:/sin-acceso");
  });

  it("con el permiso, devuelve el operador", async () => {
    resolved = operator("ok", "viewer");
    expect(await outcome(variant("read"))).toBe("operator:ok");
  });
});

describe("requireOperator sin el permiso (079, 2.2 y 2.3)", () => {
  it("vuelve a la misma página con el aviso, tras invalidar el layout", async () => {
    resolved = operator("ok", "qa_operator");
    expect(await outcome(action("money"))).toBe("redirect:/partners/p-1?tab=wallet&sin-permiso=1");
    expect(revalidated).toEqual([["/", "layout"]]);
  });

  it("deja una línea operator.permission_denied sin los argumentos de la acción", async () => {
    resolved = operator("ok", "viewer");
    await outcome(action("delete"));
    expect(warn).toHaveBeenCalledTimes(1);
    const line = JSON.parse(String(warn.mock.calls[0]?.[0]));
    expect(line).toEqual({
      event: "operator.permission_denied",
      operator_id: "op-1",
      role: "viewer",
      permission: "delete",
      surface: "action",
    });
  });

  it.each([
    ["sin Referer", undefined],
    ["con un Referer de otro host", "https://otro.test/partners"],
    ["con un Referer que apunta fuera", "https://admin.auphere.test//otro.test/x"],
    ["con un Referer que no es una URL", "nada"],
  ])("%s, a / con el aviso", async (_case, referer) => {
    resolved = operator("ok", "viewer");
    requestHeaders = referer ? { host: "admin.auphere.test", referer } : { host: "admin.auphere.test" };
    expect(await outcome(action("operate"))).toBe("redirect:/?sin-permiso=1");
  });
});

describe("requirePageOperator sin el permiso (079, 2.7)", () => {
  it("pinta «no encontrada» y no explica qué falta", async () => {
    resolved = operator("ok", "viewer");
    expect(await outcome(page("operate"))).toBe("not-found");
  });
});

describe("routeOperator (079, 2.5): nunca redirige", () => {
  async function route(permission: Parameters<typeof routeOperator>[0]) {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await routeOperator(permission);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
    return result;
  }

  it("sin sesión, 401", async () => {
    cookie = undefined;
    const result = await route("qa");
    expect(result).toBeInstanceOf(Response);
    expect((result as Response).status).toBe(401);
    expect(await (result as Response).json()).toEqual({ error: "unauthorized" });
  });

  it.each([
    ["con la cuenta deshabilitada", operator("disabled")],
    ["con un rol desconocido", operator("ok", "owner")],
    ["sin el permiso", operator("ok", "viewer")],
  ])("%s, 403", async (_case, op) => {
    resolved = op;
    const result = await route("qa");
    expect((result as Response).status).toBe(403);
    expect(await (result as Response).json()).toEqual({ error: "forbidden" });
  });

  it("con el permiso, devuelve el operador", async () => {
    resolved = operator("ok", "qa_operator");
    const result = await route("qa");
    expect(result).not.toBeInstanceOf(Response);
    expect((result as { id: string }).id).toBe("op-1");
  });
});
