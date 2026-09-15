/**
 * El canje del código de escritorio — spec 009, Requisito 4.
 *
 * Este fichero existe por un fallo que se desplegó y que ninguna prueba veía.
 *
 * La cáscara canjeaba llamando **directamente a la API**, y esa ruta exige la
 * credencial de servicio del BFF (`require_console_service`, decidido a raíz de
 * la suite de aislamiento). Staging contestaba `401 Missing bearer token` y el
 * inicio de sesión no terminaba nunca: la persona entraba en el navegador y la
 * aplicación seguía fuera.
 *
 * Y detrás había un segundo fallo del mismo error: la API devuelve el token en
 * JSON, y la sesión de la aplicación **es una cookie del origen de la consola**.
 * Aunque el 401 desapareciera, sin `Set-Cookie` la aplicación seguiría fuera.
 *
 * Por eso el canje vive aquí: es el único sitio que tiene la credencial de
 * servicio y a la vez puede poner la cookie.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";

// `vi.mock` se eleva por encima del fichero, así que lo que use su fábrica
// tiene que nacer en un `vi.hoisted` — si no, la clase todavía no existe.
const h = vi.hoisted(() => {
  class FakeBackendError extends Error {
    status: number;
    constructor(status: number) {
      super(`backend ${status}`);
      this.status = status;
    }
  }
  return { FakeBackendError, redeem: vi.fn(), setCookie: vi.fn() };
});
const { redeem: redeemSessionCode, setCookie: setSessionToken, FakeBackendError } = h;

vi.mock("@/lib/backend", () => ({
  consoleService: { redeemSessionCode: (body: unknown) => h.redeem(body) },
  BackendError: h.FakeBackendError,
}));
vi.mock("@/lib/session", () => ({
  setSessionToken: (token: string, expiresAt?: string) => h.setCookie(token, expiresAt),
}));

import { POST } from "../redeem/route";

function post(body: unknown): Request {
  return new Request("https://console.staging.auphere.com/api/desktop/redeem", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const GOOD = { code: "ABCD2345", code_verifier: "v".repeat(43) };

describe("POST /api/desktop/redeem", () => {
  beforeEach(() => {
    redeemSessionCode.mockReset();
    setSessionToken.mockReset();
  });

  it("canja con la credencial de SERVICIO y pone la cookie de sesión", async () => {
    redeemSessionCode.mockResolvedValue({
      session_token: "un-token-opaco",
      expires_at: "2026-09-22T00:00:00+00:00",
    });

    const res = await POST(post(GOOD));

    expect(redeemSessionCode).toHaveBeenCalledWith(GOOD);
    // Lo que hace que la aplicación entre: la cookie, no el JSON.
    expect(setSessionToken).toHaveBeenCalledWith("un-token-opaco", "2026-09-22T00:00:00+00:00");
    expect(res.status).toBe(204);
  });

  it("nunca devuelve el token en el cuerpo: la cáscara no guarda credenciales", async () => {
    redeemSessionCode.mockResolvedValue({
      session_token: "un-token-opaco",
      expires_at: "2026-09-22T00:00:00+00:00",
    });

    const res = await POST(post(GOOD));

    expect(await res.text()).not.toContain("un-token-opaco");
  });

  it("código rechazado por la API: 401 y NINGUNA cookie", async () => {
    redeemSessionCode.mockRejectedValue(new FakeBackendError(422));

    const res = await POST(post(GOOD));

    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ code: "session_code_invalid" });
    expect(setSessionToken).not.toHaveBeenCalled();
  });

  it.each([
    ["sin code", { code_verifier: "v".repeat(43) }],
    ["sin code_verifier", { code: "ABCD2345" }],
    ["verifier demasiado corto", { code: "ABCD2345", code_verifier: "corto" }],
    ["cuerpo vacío", {}],
  ])("%s: 400 y no se llega a llamar a la API", async (_caso, body) => {
    const res = await POST(post(body));

    expect(res.status).toBe(400);
    expect(redeemSessionCode).not.toHaveBeenCalled();
    expect(setSessionToken).not.toHaveBeenCalled();
  });
});
