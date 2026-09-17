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

/**
 * Spec 010 — las formas nuevas del armazón pasan por la misma puerta.
 *
 * El estado del puesto, la puesta en marcha y la vuelta del navegador llevan
 * datos que **parecen** inocentes, y ahí está el riesgo: si alguien añade un
 * campo llamado `session_id` a un objeto que ya viaja, nadie se entera. Este
 * bloque lo envenena a propósito.
 */
describe("lo que empuja el armazón sale igual de limpio (spec 010)", () => {
  it("el estado del puesto pierde cualquier rastro de sesión y conserva lo que sirve", () => {
    const estado = redact({
      status: "conectada",
      machine_name: "MacBook de Luis",
      since: "2026-09-17T20:10:00Z",
      cause: null,
      actions: ["directorios", "desemparejar"],
      // Lo que no debería estar y algún día estará.
      session: "abc",
      pairing_token: "secreto",
      nested: { credential: "c", missing_directories: 2 },
    }) as Record<string, unknown>;

    expect(hasForbiddenKey(estado)).toBe(false);
    expect(estado.status).toBe("conectada");
    expect(estado.machine_name).toBe("MacBook de Luis");
    expect(estado.actions).toEqual(["directorios", "desemparejar"]);
    expect((estado.nested as Record<string, unknown>).missing_directories).toBe(2);
  });

  it("la puesta en marcha y la vuelta del navegador tampoco filtran", () => {
    const setup = redact({
      steps: [
        { key: "maquina_emparejada", state: "hecho", session_cookie: "x" },
        { key: "primer_teammate", state: "pendiente", section: "hoy" },
      ],
    }) as Record<string, unknown>;
    expect(hasForbiddenKey(setup)).toBe(false);
    expect((setup.steps as Array<Record<string, unknown>>)[1]?.state).toBe("pendiente");

    const vuelta = redact({ kind: "payment", plan: "pro", usage: { used_pct: 34 }, authorization: "Bearer x" });
    expect(hasForbiddenKey(vuelta)).toBe(false);
  });

  it("el código de emparejamiento no vuelve por el canal", () => {
    // Se teclea, se canjea en el principal y ahí muere: si algún día alguien
    // lo devolviera dentro de una respuesta, `redact` no lo quitaría —no casa
    // con ninguna clave prohibida—, así que la garantía es **no ponerlo**.
    // Este test fija lo que sí se puede devolver.
    const respuesta = redact({ ok: true, machine_name: "MacBook de Luis" }) as Record<string, unknown>;
    expect(Object.keys(respuesta).sort()).toEqual(["machine_name", "ok"]);
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
