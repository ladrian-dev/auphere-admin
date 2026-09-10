/**
 * Spec 002 — el ciclo de vida con identidad: canje, almacén, renovación,
 * puerta de sesión, desemparejar y directorio por cliente.
 */
import { describe, expect, it, vi } from "vitest";

import { AppRuntime, RENEW_BEFORE_MS } from "../src/app-runtime.js";
import { CredentialStore, type Cipher, type FileStore } from "../src/credential-store.js";
import { BridgeRejected, PairingFailed } from "../src/http-transport.js";

const cipher: Cipher = {
  isAvailable: () => true,
  encrypt: (t) => Buffer.from(t, "utf8").reverse(),
  decrypt: (b) => Buffer.from(b).reverse().toString("utf8"),
};
function file(): FileStore {
  let bytes: Buffer | null = null;
  return { read: () => bytes, write: (b) => (bytes = Buffer.from(b)), remove: () => (bytes = null) };
}

function transport(over: Record<string, unknown> = {}) {
  return {
    send: vi.fn().mockResolvedValue(undefined),
    poll: vi.fn().mockResolvedValue([]),
    pollAll: vi.fn().mockResolvedValue({ work: [], links: [] }),
    pair: vi.fn().mockResolvedValue({
      deviceId: "d1", credential: "tok1", generation: 1, expiresAt: new Date(Date.now() + 12 * 3600e3).toISOString(),
      partnerSlug: "p", principalId: "luis", displayName: "mac.local",
    }),
    renew: vi.fn().mockResolvedValue({ credential: "tok2", generation: 2, expiresAt: new Date(Date.now() + 12 * 3600e3).toISOString() }),
    declareLink: vi.fn().mockResolvedValue(undefined),
    useToken: vi.fn(),
    ...over,
  };
}

function runtime(t = transport(), store = new CredentialStore(cipher, file())) {
  const app = new AppRuntime({
    consoleUrl: "https://console.auphere.com",
    transport: t,
    approvals: { pending: vi.fn().mockResolvedValue([]), answer: vi.fn().mockResolvedValue(true) },
    store,
    machine: { hostname: "mac.local", platform: "macos" },
    fs: { exists: () => true, isDirectory: () => true, realpath: (p) => p, canRead: () => true },
  });
  return { app, t, store };
}

describe("emparejar (Historia 1)", () => {
  it("sin persona dentro no se empareja: la barra lo dice", async () => {
    const { app, t } = runtime();
    await app.pair("K7MP-4XQ2");
    expect(t.pair).not.toHaveBeenCalled();
    expect(app.barState.status).toBe("sin_emparejar");
  });

  it("con persona: canjea, guarda cifrada, usa el token y arranca el puente", async () => {
    const { app, t, store } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    expect(t.pair).toHaveBeenCalledWith({ code: "K7MP-4XQ2", hostname: "mac.local", platform: "macos" });
    expect(store.get("luis")?.token).toBe("tok1");
    expect(t.useToken).toHaveBeenCalledWith("tok1");
    expect(app.barState.status).toBe("conectada");
    expect(app.barState.machine?.displayName).toBe("mac.local");
    expect(t.send).toHaveBeenCalled();
  });

  it("un código que no vale deja la barra en sin_emparejar con el motivo, y nada guardado", async () => {
    const t = transport({ pair: vi.fn().mockRejectedValue(new PairingFailed("pairing_code_invalid")) });
    const { app, store } = runtime(t);
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("XXXX-XXXX");
    expect(app.barState).toMatchObject({ status: "sin_emparejar", lastError: { code: "pairing_code_invalid" } });
    expect(store.users()).toEqual([]);
  });
});

describe("la puerta de sesión (11.1, Historia 5)", () => {
  it("la misma persona vuelve sin código: se restaura y arranca", async () => {
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: new Date(Date.now() + 1e8).toISOString(), partnerSlug: "p", displayName: "Mac de Luis" });
    const { app, t } = runtime(transport(), store);
    await app.applyGate({ kind: "start", userId: "luis", credential: store.get("luis")! });
    expect(app.barState.status).toBe("conectada");
    expect(t.useToken).toHaveBeenCalledWith("tok1");
    expect(app.localToolsOffered()).toBe(true);
  });

  it("cerrar sesión para el latido, retira las herramientas y conserva la credencial", async () => {
    const { app, t, store } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    const sends = t.send.mock.calls.length;
    await app.applyGate({ kind: "stop", reason: "anonymous" });
    await app.tick();
    expect(t.send.mock.calls.length).toBe(sends);
    expect(app.barState.status).toBe("sin_sesion");
    expect(app.localToolsOffered()).toBe(false);
    expect(store.get("luis")?.token).toBe("tok1");
  });

  it("otra persona ve «emparejada por otra persona», sin nombre y sin credencial ajena", async () => {
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac de Luis" });
    const { app, t } = runtime(transport(), store);
    await app.applyGate({ kind: "pair_needed", userId: "daniela", pairedByOther: true });
    expect(app.barState).toMatchObject({ status: "sin_emparejar", pairedByOther: true });
    expect(app.barState.machine).toBeUndefined();
    expect(t.useToken).not.toHaveBeenCalled();
  });
});

describe("renovar y ser rechazada (10, 11.3)", () => {
  it("renueva sola cuando queda menos de seis horas, y guarda la nueva", async () => {
    const soon = new Date(Date.now() + RENEW_BEFORE_MS - 60_000).toISOString();
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: soon, partnerSlug: "p", displayName: "Mac" });
    const { app, t } = runtime(transport(), store);
    await app.applyGate({ kind: "start", userId: "luis", credential: store.get("luis")! });
    await app.tick();
    expect(t.renew).toHaveBeenCalled();
    expect(store.get("luis")?.token).toBe("tok2");
    expect(store.get("luis")?.generation).toBe(2);
  });

  it("archivada desde la consola → la barra lo dice y la credencial se olvida", async () => {
    const t = transport({ send: vi.fn().mockRejectedValue(new BridgeRejected("device_archived", "archivada_consola")) });
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac" });
    const { app } = runtime(t, store);
    await app.applyGate({ kind: "start", userId: "luis", credential: store.get("luis")! });
    expect(app.barState.status).toBe("archivada_desde_consola");
    expect(store.get("luis")).toBeUndefined();
    expect(app.localToolsOffered()).toBe(false);
  });

  it("un 401 o pairing_required → volver a emparejar", async () => {
    const t = transport({ send: vi.fn().mockRejectedValue(new BridgeRejected("pairing_required")) });
    const { app } = runtime(t);
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    expect(app.barState.status).toBe("volver_a_emparejar");
  });

  it("y un fallo de red sigue siendo reconectando, sin olvidar nada", async () => {
    const t = transport();
    const { app, store } = runtime(t);
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    t.send.mockRejectedValue(new Error("sin red"));
    await app.tick();
    expect(app.barState.status).toBe("reconectando");
    expect(store.get("luis")?.token).toBe("tok1");
  });
});

describe("desemparejar y directorios (11.2, 7)", () => {
  it("desemparejar olvida la credencial, para el latido y vuelve a sin_emparejar", async () => {
    const { app, t, store } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    app.unpair();
    expect(store.get("luis")).toBeUndefined();
    expect(app.barState.status).toBe("sin_emparejar");
    const sends = t.send.mock.calls.length;
    await app.tick();
    expect(t.send.mock.calls.length).toBe(sends);
  });

  it("los vínculos del sondeo llegan a la barra, y el directorio se declara por cliente", async () => {
    const t = transport({
      pollAll: vi.fn().mockResolvedValue({ work: [], links: [{ clientRef: "cultor", clientName: "Cultor", workdir: null, needsDirectory: true }] }),
    });
    const { app } = runtime(t);
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    expect(app.barState.links).toEqual([{ clientRef: "cultor", clientName: "Cultor", needsDirectory: true }]);
    expect(app.workdirFor("cultor")).toBeNull();
    const result = await app.declareDirectory("cultor", async () => "/Users/luis/cultor");
    expect(result).toEqual({ kind: "declared", workdir: "/Users/luis/cultor" });
    expect(t.declareLink).toHaveBeenCalledWith(expect.objectContaining({ clientRef: "cultor", workdir: "/Users/luis/cultor" }));
  });

  it("un trabajo de un cliente sin directorio no se ejecuta (7.5)", () => {
    const { app } = runtime();
    expect(app.workdirFor("sin-directorio")).toBeNull();
  });
});

describe("aprobaciones solo para la persona con sesión (5.3, Historia 5)", () => {
  it("sin puente corriendo no se pregunta a la cola: se levanta, no se devuelve vacío", async () => {
    const { app } = runtime();
    await app.applyGate({ kind: "stop", reason: "anonymous" });
    await expect(app.pendingApprovals()).rejects.toThrow(/no se contestan aprobaciones/);
    await expect(app.answerApproval("spawn:1", true)).rejects.toThrow();
  });

  it("otra persona con sesión en la máquina de Luis tampoco contesta por él", async () => {
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac" });
    const { app } = runtime(transport(), store);
    await app.applyGate({ kind: "pair_needed", userId: "daniela", pairedByOther: true });
    await expect(app.pendingApprovals()).rejects.toThrow();
  });

  it("con la persona dueña dentro, la cola se lee con normalidad", async () => {
    const { app } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    await app.pair("K7MP-4XQ2");
    expect(await app.pendingApprovals()).toEqual([]);
  });
});
