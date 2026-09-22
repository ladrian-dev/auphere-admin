/**
 * Spec 002 — el ciclo de vida con identidad: canje, almacén, renovación,
 * puerta de sesión, desemparejar y directorio por cliente.
 */
import { describe, expect, it, vi } from "vitest";

import { AppRuntime, type AppRuntimeOptions, RENEW_BEFORE_MS } from "../src/app-runtime.js";
import { CredentialStore, type Cipher, type FileStore } from "../src/credential-store.js";
import { BridgeRejected } from "../src/http-transport.js";
import { SessionGate } from "../src/session-gate.js";

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

/**
 * Registrar con la sesión (spec 012), que es lo que sustituyó al canje del
 * código. Varias pruebas de abajo lo usan como **preparación** —lo que miran es
 * el latido, la puerta o las aprobaciones—, así que vive aquí y no repetido.
 */
function registered(over: Partial<{ deviceId: string; token: string }> = {}) {
  return vi.fn(async () => ({
    kind: "registered" as const,
    machine: {
      deviceId: over.deviceId ?? "dev-1",
      credential: over.token ?? "tok1",
      generation: 1,
      expiresAt: new Date(Date.now() + 12 * 3600 * 1000).toISOString(),
      partnerSlug: "auphere",
      displayName: "mac.local",
    },
  }));
}

function runtime(
  t = transport(),
  store = new CredentialStore(cipher, file()),
  register: AppRuntimeOptions["registerMachine"] = registered(),
) {
  const app = new AppRuntime({
    consoleUrl: "https://console.auphere.com",
    transport: t,
    approvals: { pending: vi.fn().mockResolvedValue([]), answer: vi.fn().mockResolvedValue(true) },
    store,
    machine: { hostname: "mac.local", platform: "macos" },
    fs: { exists: () => true, isDirectory: () => true, realpath: (p) => p, canRead: () => true },
    registerMachine: register,
    installId: "instalacion-de-prueba",
  });
  return { app, t, store, register };
}

/**
 * El banner de «sin emparejar» — el fallo `banner-sin-emparejar-no-se-va`.
 *
 * WHEN la persona empareja la máquina
 * THEN el sistema DEBE volver a derivar el veredicto de la puerta de sesión.
 *
 * El banner de la pantalla (`App.tsx:266`) se pinta con `pair_needed`, que sale
 * de `gate.onDecision` y solo se vuelve a evaluar cuando cambia la cookie o
 * cuando se pierde la sesión. Emparejar cambia el **almacén**, que es de donde
 * la puerta saca su veredicto, pero no tocaba ni la cookie ni la sesión: el
 * banner se quedaba mintiendo mientras la barra decía lo contrario.
 *
 * **Manda la puerta, y por eso el arreglo es volver a derivar y no copiar.** La
 * puerta lee la credencial donde está; la barra refleja eventos del puente, que
 * son consecuencia. Fabricar un `app:session` desde el canje mentiría el día que
 * la puerta tenga una condición más.
 */
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
    const sends = t.send.mock.calls.length;
    await app.applyGate({ kind: "stop", reason: "anonymous" });
    await app.tick();
    expect(t.send.mock.calls.length).toBe(sends);
    expect(app.barState.status).toBe("sin_sesion");
    expect(app.localToolsOffered()).toBe(false);
    expect(store.get("luis")?.token).toBe("tok1");
  });

  it("otra persona en la misma máquina recibe LA SUYA, nunca la credencial ajena", async () => {
    /**
     * **Esto cambió con la spec 012, y el cambio es el correcto.**
     *
     * Antes, quien entraba en una máquina que otra persona había emparejado
     * veía «emparejada por otra persona» y se quedaba sin poder trabajar: no
     * había forma de darle una credencial propia sin pedir otro código.
     *
     * Con el registro por sesión la hay, y es lo que la spec declara en sus
     * casos límite: **dos personas en la misma máquina física, cada una con su
     * credencial**. Lo que sigue sin pasar —y es lo que este test defiende— es
     * que vea la ajena.
     */
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac de Luis" });
    const { app, t } = runtime(transport(), store, registered({ deviceId: "d2", token: "tok-daniela" }));

    await app.applyGate({ kind: "pair_needed", userId: "daniela", pairedByOther: true });

    expect(store.get("daniela")?.token).toBe("tok-daniela");
    expect(t.useToken).toHaveBeenCalledWith("tok-daniela");
    // La de Luis sigue donde estaba y no se toca.
    expect(store.get("luis")?.token).toBe("tok1");
  });

  it("y si no se le puede registrar una propia, se queda fuera en vez de usar la ajena", async () => {
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac de Luis" });
    const sinRegistro = vi.fn(async () => ({ kind: "sign_in_again" as const }));
    const { app, t } = runtime(transport(), store, sinRegistro);

    await app.applyGate({ kind: "pair_needed", userId: "daniela", pairedByOther: true });

    expect(store.get("daniela")).toBeUndefined();
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
    expect(app.barState.status).toBe("volver_a_emparejar");
  });

  it("y un fallo de red sigue siendo reconectando, sin olvidar nada", async () => {
    const t = transport();
    const { app, store } = runtime(t);
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
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
    // Spec 010 R8.4: el vínculo lleva además **dónde trabaja**, para que el
    // diálogo de directorios pueda enseñarlo. Aquí todavía no hay ninguno.
    expect(app.barState.links).toEqual([
      { clientRef: "cultor", clientName: "Cultor", needsDirectory: true, workdir: null },
    ]);
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

describe("la barra habla el idioma de la cuenta (12.2)", () => {
  it("el idioma llega a la barra con la persona y sobrevive a desemparejar", async () => {
    const { app } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false, locale: "es" });
    expect(app.barState.locale).toBe("es");
    app.unpair();
    expect(app.barState.locale).toBe("es");
  });
});

describe("aprobaciones solo para la persona con sesión (5.3, Historia 5)", () => {
  it("sin puente corriendo no se pregunta a la cola: se levanta, no se devuelve vacío", async () => {
    const { app } = runtime();
    await app.applyGate({ kind: "stop", reason: "anonymous" });
    await expect(app.pendingApprovals()).rejects.toThrow(/no se contestan aprobaciones/);
    await expect(app.answerApproval("spawn:1", true)).rejects.toThrow();
  });

  it("otra persona sin credencial propia no contesta por Luis", async () => {
    /**
     * El invariante de 5.3 no cambia —nadie contesta las aprobaciones de
     * otro—, pero el montaje sí: desde la spec 012, quien entra en una máquina
     * ajena **recibe la suya** y lee su propia cola con normalidad. Lo que deja
     * a alguien sin poder contestar es no tener credencial, que es lo que este
     * test monta ahora.
     */
    const store = new CredentialStore(cipher, file());
    store.put("luis", { deviceId: "d1", token: "tok1", generation: 1, expiresAt: "2099-01-01T00:00:00Z", partnerSlug: "p", displayName: "Mac" });
    const sinRegistro = vi.fn(async () => ({ kind: "unavailable" as const }));
    const { app } = runtime(transport(), store, sinRegistro);

    await app.applyGate({ kind: "pair_needed", userId: "daniela", pairedByOther: true });

    await expect(app.pendingApprovals()).rejects.toThrow();
  });

  it("con la persona dueña dentro, la cola se lee con normalidad", async () => {
    const { app } = runtime();
    await app.applyGate({ kind: "pair_needed", userId: "luis", pairedByOther: false });
    expect(await app.pendingApprovals()).toEqual([]);
  });
});

/**
 * El canje del código de sesión — spec 009, Historia 2.
 *
 * **Lo que el runtime hace aquí es muy poco, y ése es el diseño.** No valida el
 * código, no guarda nada y no ve ningún secreto: entrega ocho caracteres al
 * BFF con el `fetch` de la partición humana, y lo que vuelve lo guarda la
 * partición sola. Si sale bien, lo único que el runtime hace es **volver a
 * preguntarle a la puerta**, exactamente como al emparejar.
 */
describe("iniciar sesión por el navegador (spec 009, 2ª enmienda)", () => {
  function conNavegador(responder: () => Promise<{ ok: boolean }>) {
    const store = new CredentialStore(cipher, file());
    const { app } = runtime(transport(), store);
    const gate = new SessionGate({
      store,
      whoami: {
        whoami: vi.fn().mockResolvedValue({ kind: "member", userId: "luis", partnerSlug: "p" }),
      },
    });
    const seen: string[] = [];
    gate.onDecision((d) => seen.push(d.kind));
    app.onIdentityChanged(() => void gate.refresh());
    app.useBrowserSignIn(responder);
    return { app, seen };
  }

  it("un inicio de sesión correcto vuelve a preguntarle a la puerta", async () => {
    const { app, seen } = conNavegador(async () => ({ ok: true }));
    await app.signInWithBrowser();
    await vi.waitFor(() => expect(seen.length).toBeGreaterThan(0));
  });

  it("uno fallido lo dice en la barra y NO avisa de identidad", async () => {
    const { app, seen } = conNavegador(async () => ({ ok: false }));
    await app.signInWithBrowser();
    expect(app.barState.lastError?.code).toBe("session_code_invalid");
    expect(seen).toEqual([]);
  });

  it("sin nadie que inicie sesión, lo dice en vez de quedarse callado", async () => {
    const store = new CredentialStore(cipher, file());
    const { app } = runtime(transport(), store);
    // Nadie llamó a `useBrowserSignIn`: es un error de cableado, y la barra lo
    // cuenta igual en vez de fingir que no pasó nada.
    await app.signInWithBrowser();
    expect(app.barState.lastError?.code).toBe("session_code_invalid");
  });
});
