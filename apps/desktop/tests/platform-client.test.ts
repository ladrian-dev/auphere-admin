/**
 * Requisitos 12.2 y 12.3 — el principal habla con el BFF con la sesión de la
 * partición de la persona, y una respuesta sin sesión es «sin sesión», no un error.
 */
import { describe, expect, it } from "vitest";

import { PlatformClient, SessionLost } from "../src/platform-client.js";

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

describe("PlatformClient", () => {
  it("llama al origen de la consola con el fetch inyectado y Accept JSON", async () => {
    let url = "";
    let init: RequestInit | undefined;
    const client = new PlatformClient({
      consoleUrl: "http://localhost:3110/algo",
      fetch: async (u, i) => {
        url = u;
        init = i;
        return json([{ id: "1" }]);
      },
    });
    const res = await client.request<Array<{ id: string }>>("/api/teammates");
    expect(url).toBe("http://localhost:3110/api/teammates");
    expect(JSON.stringify(init?.headers)).toMatch(/application\/json/);
    expect(res.ok && res.data[0]?.id).toBe("1");
  });

  it("401 y una redirección al login son «sin sesión»", async () => {
    for (const status of [401, 302, 307]) {
      const client = new PlatformClient({ consoleUrl: "http://c.test", fetch: async () => new Response("", { status }) });
      await expect(client.request("/api/teammates")).rejects.toBeInstanceOf(SessionLost);
    }
  });

  it("403 no_membership es «sin sesión» con su motivo; otro 403 es un error normal", async () => {
    const noMember = new PlatformClient({ consoleUrl: "http://c.test", fetch: async () => json({ code: "no_membership" }, 403) });
    await expect(noMember.request("/api/teammates")).rejects.toMatchObject({ reason: "no_membership" });
    const forbidden = new PlatformClient({ consoleUrl: "http://c.test", fetch: async () => json({ detail: "Missing permission" }, 403) });
    const res = await forbidden.request("/api/teammates");
    expect(res).toMatchObject({ ok: false, status: 403, detail: "Missing permission" });
  });

  it("una página HTML en vez de JSON con error es «sin sesión» (el proxy manda al login)", async () => {
    const client = new PlatformClient({ consoleUrl: "http://c.test", fetch: async () => new Response("<html>login</html>", { status: 200 }) });
    const res = await client.request("/api/teammates");
    expect(res.ok && res.data).toBeNull();
  });

  it("sin red devuelve un resultado, no una excepción", async () => {
    const client = new PlatformClient({ consoleUrl: "http://c.test", fetch: async () => { throw new Error("offline"); } });
    expect(await client.request("/api/teammates")).toMatchObject({ ok: false, status: 0, detail: "network" });
  });

  it("los cuerpos JSON van con método y Content-Type", async () => {
    let init: RequestInit | undefined;
    const client = new PlatformClient({ consoleUrl: "http://c.test", fetch: async (_u, i) => { init = i; return json({}); } });
    await client.request("/api/teammates", { method: "POST", body: { name: "Sofía" } });
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ name: "Sofía" }));
  });
});
