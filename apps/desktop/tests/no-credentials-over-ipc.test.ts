/**
 * Requisito 12.2 (garantía 3) — nada que salga por el canal lleva una sesión,
 * una cookie, un token ni una credencial.
 *
 * Se envenena un `PlatformClient` con cuerpos que las llevan a varias
 * profundidades y se afirma que lo que llega al renderer no las tiene. Y se
 * recorre el fuente del `preload`: no expone `ipcRenderer`, no lee cookies.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { FORBIDDEN_KEYS, hasForbiddenKey, redact } from "../src/app-ipc.js";
import { PlatformClient } from "../src/platform-client.js";

const POISON = {
  id: "t1",
  name: "Sofía",
  session: "abc",
  cookie: "nexus-console.session=xyz",
  nested: { token: "jwt", Authorization: "Bearer x", deeper: [{ credential: "c", ok: 1 }], fine: "sí" },
  list: [{ access_token: "a" }, { name: "Nilo" }],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("redact quita lo prohibido a cualquier profundidad", () => {
  it("elimina claves de sesión, cookie, token y credencial y conserva el resto", () => {
    const out = redact(POISON) as Record<string, unknown>;
    expect(hasForbiddenKey(out)).toBe(false);
    expect(out.name).toBe("Sofía");
    expect((out.nested as Record<string, unknown>).fine).toBe("sí");
    expect(((out.nested as Record<string, unknown>).deeper as unknown[])[0]).toEqual({ ok: 1 });
    expect(out.list).toEqual([{}, { name: "Nilo" }]);
  });

  it("la expresión cubre los nombres que se usan de verdad", () => {
    for (const k of ["session", "Session", "cookie", "token", "access_token", "credential", "Authorization", "secret", "password"]) {
      expect(FORBIDDEN_KEYS.test(k), k).toBe(true);
    }
    expect(FORBIDDEN_KEYS.test("name")).toBe(false);
  });
});

describe("el PlatformClient nunca devuelve lo prohibido (12.2)", () => {
  it("un cuerpo envenenado sale limpio, en éxito y en error", async () => {
    const okClient = new PlatformClient({ consoleUrl: "http://console.test", fetch: async () => jsonResponse(POISON) });
    const ok = await okClient.request<Record<string, unknown>>("/api/teammates");
    expect(ok.ok && hasForbiddenKey(ok.data)).toBe(false);
    const errClient = new PlatformClient({
      consoleUrl: "http://console.test",
      fetch: async () => jsonResponse({ detail: "no", code: "x", ...POISON }, 422),
    });
    const err = await errClient.request("/api/teammates");
    expect(err.ok).toBe(false);
    expect(hasForbiddenKey(err)).toBe(false);
  });

  it("nunca manda cookies ni tokens por su cuenta: solo usa el fetch de la partición", async () => {
    const seen: RequestInit[] = [];
    const client = new PlatformClient({
      consoleUrl: "http://console.test",
      fetch: async (_url, init) => {
        seen.push(init ?? {});
        return jsonResponse([]);
      },
    });
    await client.request("/api/teammates");
    const headers = JSON.stringify(seen[0]?.headers ?? {});
    expect(headers).not.toMatch(/cookie|authorization|bearer/i);
  });
});

describe("el preload no expone ipcRenderer ni lee cookies", () => {
  const preload = readFileSync(new URL("../src/electron/app-preload.ts", import.meta.url), "utf8");
  const bridge = readFileSync(new URL("../src/app-bridge.ts", import.meta.url), "utf8");
  it("no hay `exposeInMainWorld` de ipcRenderer, ni document.cookie, ni require en el renderer", () => {
    expect(preload).toMatch(/buildAppBridge\(ipcRenderer\)/);
    expect(preload).not.toMatch(/exposeInMainWorld\("ipc/);
    expect(preload + bridge).not.toMatch(/document\.cookie|localStorage|safeStorage|credential-store/);
  });
});
