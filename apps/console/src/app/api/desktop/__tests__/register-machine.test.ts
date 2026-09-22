/**
 * Registrar la máquina con la sesión — spec 012, Requisito 3.
 *
 * Su hermana `redeem.test.ts` existe por un fallo que se desplegó: la cáscara
 * llamaba directamente a la API, que exige la credencial de servicio del BFF, y
 * recibía `401 Missing bearer token`. Aquí el mismo camino y la misma lección —
 * con una diferencia que conviene tener presente al leer: **ésta sí devuelve
 * cuerpo**, porque lo que entrega es una credencial que la aplicación guarda
 * cifrada, no una cookie que viaja sola.
 *
 * Los dos bloques que importan son los últimos: qué se contesta cuando se
 * rechaza. El tope dice que es el tope —es información de quien pregunta, y
 * saberlo es lo que le dice qué hacer—; lo demás comparte cuerpo, porque «no hay
 * sesión» y «la sesión caducó» llevan al mismo sitio.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => {
  class FakeBackendError extends Error {
    status: number;
    constructor(status: number) {
      super(`backend ${status}`);
      this.status = status;
    }
  }
  return { FakeBackendError, register: vi.fn(), resolve: vi.fn() };
});

vi.mock("@/lib/backend", () => ({
  backendFor: () => ({ registerMachine: (body: unknown) => h.register(body) }),
  BackendError: h.FakeBackendError,
}));
vi.mock("@/lib/principal", () => ({
  resolvePrincipal: () => h.resolve(),
}));

const { POST } = await import("../register-machine/route");

const PRINCIPAL = { userId: "u-1", partnerId: "p-1", role: "owner" };
const REGISTERED = {
  device_id: "d-1",
  credential: "una-credencial",
  generation: 1,
  expires_at: "2026-09-23T00:00:00Z",
  partner_slug: "auphere",
  principal_id: "u-1",
  display_name: "mac-de-prueba.local",
};

function body(over: Record<string, unknown> = {}): Request {
  return new Request("http://localhost/api/desktop/register-machine", {
    method: "POST",
    body: JSON.stringify({
      hostname: "mac-de-prueba.local",
      platform: "macos",
      install_id: "instalacion-de-esta-maquina",
      ...over,
    }),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  h.resolve.mockResolvedValue({ kind: "ok", principal: PRINCIPAL });
  h.register.mockResolvedValue(REGISTERED);
});

describe("con sesión confirmada", () => {
  it("registra la máquina y devuelve la credencial una vez", async () => {
    const res = await POST(body());

    expect(res.status).toBe(201);
    expect(await res.json()).toEqual(REGISTERED);
  });

  it("no acepta un identificador de instalación corto", async () => {
    // El mínimo lo declara la API; comprobarlo aquí evita gastar un token en
    // una llamada que ya se sabe que no vale.
    const res = await POST(body({ install_id: "corto" }));

    expect(res.status).toBe(400);
    expect(h.register).not.toHaveBeenCalled();
  });

  it("no acepta una plataforma inventada", async () => {
    const res = await POST(body({ platform: "commodore" }));

    expect(res.status).toBe(400);
    expect(h.register).not.toHaveBeenCalled();
  });
});

describe("cuando se rechaza", () => {
  it("sin sesión no se llama a la API siquiera", async () => {
    h.resolve.mockResolvedValue({ kind: "anonymous" });

    const res = await POST(body());

    expect(res.status).toBe(401);
    expect(h.register).not.toHaveBeenCalled();
  });

  it("«sin sesión» y «sesión vieja» se contestan igual", async () => {
    // Las dos llevan al mismo sitio —entrar de nuevo—, así que separarlas
    // añadiría un detalle sin uso.
    h.resolve.mockResolvedValue({ kind: "anonymous" });
    const sinSesion = await POST(body());

    h.resolve.mockResolvedValue({ kind: "ok", principal: PRINCIPAL });
    h.register.mockRejectedValue(new h.FakeBackendError(401));
    const vieja = await POST(body());

    expect(sinSesion.status).toBe(vieja.status);
    expect(await sinSesion.json()).toEqual(await vieja.json());
  });

  it("el tope dice que es el tope, porque saberlo es lo que ayuda", async () => {
    h.register.mockRejectedValue(new h.FakeBackendError(409));

    const res = await POST(body());

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ code: "machine_cap_reached" });
  });
});
