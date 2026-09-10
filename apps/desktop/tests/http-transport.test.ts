/**
 * El transporte real del puente — Requisitos 6.1 y 6.2.
 *
 * Cierra el recorrido: hasta ahora `AppRuntime` hablaba con un talón porque el
 * otro extremo no existía. Ya existe.
 *
 * Lo que se comprueba no es que llame a las rutas —eso es fontanería— sino las
 * dos propiedades que hacen que el puente sea seguro: **solo sale** y **un fallo
 * no se disfraza de silencio**.
 */
import { describe, expect, it, vi } from "vitest";

import { HttpTransport } from "../src/http-transport.js";

const ok = (body: unknown = {}) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body });

describe("solo sale (6.1)", () => {
  it("el latido va por POST y lleva la credencial del dispositivo", async () => {
    const fetch = ok();
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "dev-token", fetch });
    await t.send({ kind: "heartbeat", at: 1 });
    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(String(url)).toContain("/device/heartbeat");
    expect(init?.method).toBe("POST");
    expect(init?.headers?.Authorization).toBe("Bearer dev-token");
  });

  it("el sondeo pide, no escucha", async () => {
    const fetch = ok({ work: [] });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await t.poll();
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/device/poll");
    expect(fetch.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it("no expone ninguna forma de escuchar", () => {
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch: ok() });
    expect(Object.keys(Object.getPrototypeOf(t)).concat(Object.keys(t))).not.toContain("listen");
  });
});

describe("un fallo no se disfraza de silencio (§V)", () => {
  it("si el sondeo falla, se levanta en vez de devolver «no hay trabajo»", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await expect(t.poll()).rejects.toThrow();
  });

  it("si el latido falla, se levanta y el puente pasa a `reconectando`", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("sin red"));
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await expect(t.send({ kind: "heartbeat", at: 1 })).rejects.toThrow();
  });
});

describe("el resultado no lleva la salida del comando (§III)", () => {
  it("solo viaja qué pasó, no qué dijo", async () => {
    const fetch = ok();
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await t.send({
      kind: "execution_result",
      executionId: "11111111-1111-1111-1111-111111111111",
      outcome: "completada",
      exitCode: 0,
      childrenReaped: 0,
    });
    const body = String(fetch.mock.calls[0]?.[1]?.body ?? "");
    expect(body).toContain("execution_id");
    expect(body).not.toContain("stdout");
    expect(body).not.toContain("output");
  });
});

// ── spec 002: el canje, la renovación, los vínculos y los rechazos ─────────

import { BridgeRejected, PairingFailed } from "../src/http-transport.js";

const reply = (status: number, body: unknown = {}) =>
  vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });

describe("el canje del código (3.2, 3.3)", () => {
  it("va sin credencial y devuelve la credencial una vez", async () => {
    const fetch = reply(201, {
      device_id: "d1", credential: "tok", generation: 1, expires_at: "2026-09-10T00:00:00Z",
      partner_slug: "p", principal_id: "luis", display_name: "mac.local",
    });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", fetch, appVersion: "0.2.0" });
    const paired = await t.pair({ code: "K7MP-4XQ2", hostname: "mac.local", platform: "macos" });
    expect(paired.deviceId).toBe("d1");
    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(String(url)).toContain("/device/pair");
    expect(init?.headers?.Authorization).toBeUndefined();
    expect(JSON.parse(String(init?.body))).toMatchObject({ code: "K7MP-4XQ2", app_version: "0.2.0" });
  });

  it("un 404 es «ese código no vale», y un 429 es «espera»", async () => {
    const t404 = new HttpTransport({ baseUrl: "https://api.auphere.com", fetch: reply(404, { code: "pairing_code_invalid" }) });
    await expect(t404.pair({ code: "x", hostname: "h", platform: "macos" })).rejects.toBeInstanceOf(PairingFailed);
    const t429 = new HttpTransport({ baseUrl: "https://api.auphere.com", fetch: reply(429, { code: "pairing_rate_limited" }) });
    await expect(t429.pair({ code: "x", hostname: "h", platform: "macos" })).rejects.toMatchObject({ code: "pairing_rate_limited" });
  });
});

describe("renovar y declarar (10.1, 7.2)", () => {
  it("renovar rota la credencial que usa el transporte", async () => {
    const fetch = reply(200, { credential: "tok2", generation: 2, expires_at: "2026-09-10T12:00:00Z" });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "tok1", fetch });
    const renewed = await t.renew();
    expect(renewed.generation).toBe(2);
    await t.send({ kind: "heartbeat", at: 1 });
    expect(fetch.mock.calls[1]?.[1]?.headers?.Authorization).toBe("Bearer tok2");
  });

  it("declarar envía client_ref, workdir y las cuatro comprobaciones", async () => {
    const fetch = reply(204);
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "t", fetch });
    await t.declareLink({
      clientRef: "cultor",
      workdir: "/Users/luis/cultor",
      checks: { exists: true, is_dir: true, resolves_within: true, readable: true },
    });
    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({
      client_ref: "cultor",
      workdir: "/Users/luis/cultor",
      checks: { exists: true, is_dir: true, resolves_within: true, readable: true },
    });
  });

  it("el sondeo trae los vínculos y cuáles no tienen directorio", async () => {
    const fetch = reply(200, {
      work: [],
      links: [{ client_ref: "cultor", client_name: "Cultor", workdir: null, needs_directory: true }],
    });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "t", fetch });
    const polled = await t.pollAll();
    expect(polled.links).toEqual([{ clientRef: "cultor", clientName: "Cultor", workdir: null, needsDirectory: true }]);
  });
});

describe("un rechazo no es un fallo (§V, 11.3, 10.2)", () => {
  it("401 → unauthorized", async () => {
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "t", fetch: reply(401) });
    await expect(t.send({ kind: "heartbeat", at: 1 })).rejects.toMatchObject({ reason: "unauthorized" });
  });

  it("403 device_archived → archivada, con su motivo", async () => {
    const t = new HttpTransport({
      baseUrl: "https://api.auphere.com",
      token: "t",
      fetch: reply(403, { code: "device_archived", reason: "archivada_consola" }),
    });
    await expect(t.poll()).rejects.toMatchObject({ reason: "device_archived", detail: "archivada_consola" });
  });

  it("403 pairing_required → volver a emparejar", async () => {
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "t", fetch: reply(403, { code: "pairing_required" }) });
    await expect(t.renew()).rejects.toBeInstanceOf(BridgeRejected);
  });

  it("y un 503 sigue siendo un fallo, no un rechazo", async () => {
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "t", fetch: reply(503) });
    await expect(t.poll()).rejects.not.toBeInstanceOf(BridgeRejected);
  });
});
