import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Spec 062 (hotfix P0 del 2026-11-17): una llamada lenta o cortada a la API ya
 * no tumba la pantalla ni saca a la persona de su sesión.
 *
 * Aquel día Cloudflare atendía las llamadas de la consola desde Tokio y São
 * Paulo, y una de cada cien tardaba decenas de segundos. Tres cosas convertían
 * esa lentitud en errores:
 *  - la consulta de sesión reintentaba con el MISMO token, y la API lo rechaza
 *    por repetido (401 `replayed_jti`): la persona acababa en `/login`;
 *  - ninguna otra llamada reintentaba un fallo de conexión;
 *  - las lecturas no tenían límite: una página se quedaba colgada.
 *
 * Cada token se acuña con un contador para que se vea cuál viaja en cada intento.
 */
let svc = 0;
let prin = 0;
vi.mock("@/lib/env", () => ({ env: () => ({ NEXUS_BACKEND_URL: "http://api.test" }) }));
vi.mock("@/lib/jwt", () => ({
  mintServiceToken: async () => `svc-${++svc}`,
  mintPrincipalToken: async () => `p-${++prin}`,
}));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

const { callFor, consoleService } = await import("@/lib/backend");
const { BackendError } = await import("@/lib/backend");
type CallPrincipal = Parameters<typeof callFor>[0];

const principal = { userId: "u", partnerId: "p", role: "owner" } as unknown as CallPrincipal;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const sessionOk = () => json({ principal: { user_id: "u", email: "x@y.test", access: "ok" }, expires_at: null });

/** `fetch failed` de Node, con el código del sistema en `cause`, como lo da undici. */
const netError = (code: string) => Object.assign(new TypeError("fetch failed"), { cause: Object.assign(new Error(code), { code }) });
const timeout = () => new DOMException("The operation was aborted due to timeout", "TimeoutError");
const bearer = (call: unknown[]) => new Headers((call[1] as RequestInit).headers).get("Authorization");

describe("spec 062 — la consola aguanta una API lenta o una conexión cortada", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("consulta de sesión", () => {
    it("cada intento lleva un token nuevo: el segundo no es un 401 por repetido", async () => {
      fetchMock.mockRejectedValueOnce(timeout()).mockResolvedValueOnce(sessionOk());
      expect(await consoleService.session("tok")).toMatchObject({ user_id: "u" });
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(bearer(fetchMock.mock.calls[0]!)).not.toEqual(bearer(fetchMock.mock.calls[1]!));
    });
  });

  describe("lecturas (GET)", () => {
    it("tienen límite de tiempo", async () => {
      fetchMock.mockResolvedValueOnce(json({ ok: true }));
      await callFor(principal)("/console/me");
      expect((fetchMock.mock.calls[0]![1] as RequestInit).signal).toBeInstanceOf(AbortSignal);
    });

    it("una conexión cortada se reintenta una vez, con un token nuevo", async () => {
      fetchMock.mockRejectedValueOnce(netError("ECONNRESET")).mockResolvedValueOnce(json({ ok: 1 }));
      expect(await callFor(principal)("/console/me")).toEqual({ ok: 1 });
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(bearer(fetchMock.mock.calls[0]!)).not.toEqual(bearer(fetchMock.mock.calls[1]!));
    });

    it("pasarse de tiempo y un 502 se reintentan", async () => {
      fetchMock.mockRejectedValueOnce(timeout()).mockResolvedValueOnce(json({ ok: 1 }));
      expect(await callFor(principal)("/console/me")).toEqual({ ok: 1 });
      fetchMock.mockReset();
      fetchMock.mockResolvedValueOnce(json({ detail: "x" }, 502)).mockResolvedValueOnce(json({ ok: 2 }));
      expect(await callFor(principal)("/console/me")).toEqual({ ok: 2 });
    });

    it("solo hay un reintento: dos fallos seguidos llegan al llamante", async () => {
      fetchMock.mockRejectedValue(netError("ECONNRESET"));
      await expect(callFor(principal)("/console/me")).rejects.toThrow("fetch failed");
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("un 4xx es una respuesta y no se reintenta", async () => {
      fetchMock.mockResolvedValueOnce(json({ detail: "x" }, 403));
      await expect(callFor(principal)("/console/me")).rejects.toBeInstanceOf(BackendError);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("si quien llama cancela, no se reintenta", async () => {
      const ctrl = new AbortController();
      ctrl.abort();
      fetchMock.mockRejectedValueOnce(new DOMException("aborted", "AbortError"));
      await expect(callFor(principal)("/console/me", { signal: ctrl.signal })).rejects.toThrow("aborted");
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  describe("escrituras (POST, PUT, PATCH, DELETE)", () => {
    it("si la conexión no llegó a abrirse, se reintenta con un token nuevo: nada llegó a la API", async () => {
      fetchMock.mockRejectedValueOnce(netError("UND_ERR_CONNECT_TIMEOUT")).mockResolvedValueOnce(json({ id: 1 }));
      expect(await callFor(principal)("/console/x", { method: "POST", body: {} })).toEqual({ id: 1 });
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(bearer(fetchMock.mock.calls[0]!)).not.toEqual(bearer(fetchMock.mock.calls[1]!));
    });

    it("también cuando el fallo de conexión viene agrupado por direcciones", async () => {
      const grouped = Object.assign(new TypeError("fetch failed"), {
        cause: Object.assign(new AggregateError([Object.assign(new Error("x"), { code: "ECONNREFUSED" })]), {}),
      });
      fetchMock.mockRejectedValueOnce(grouped).mockResolvedValueOnce(json({ id: 1 }));
      expect(await callFor(principal)("/console/x", { method: "PATCH", body: {} })).toEqual({ id: 1 });
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("una conexión cortada después de enviar NO se reintenta: la escritura pudo haberse hecho", async () => {
      fetchMock.mockRejectedValueOnce(netError("ECONNRESET"));
      await expect(callFor(principal)("/console/x", { method: "POST", body: {} })).rejects.toThrow("fetch failed");
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("un 5xx NO se reintenta", async () => {
      fetchMock.mockResolvedValueOnce(json({ detail: "x" }, 503));
      await expect(callFor(principal)("/console/x", { method: "PUT", body: {} })).rejects.toMatchObject({ status: 503 });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("no tienen límite de tiempo propio: el constructor puede tardar minutos", async () => {
      fetchMock.mockResolvedValueOnce(json({ id: 1 }));
      await callFor(principal)("/console/x", { method: "POST", body: {} });
      expect((fetchMock.mock.calls[0]![1] as RequestInit).signal).toBeUndefined();
    });
  });
});
