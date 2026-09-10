/**
 * Requisitos 2.2, 2.4, 11.1 y Historia 5 — la puerta de sesión.
 *
 * Quién está dentro lo lee el proceso principal por `whoami`, con la cookie de
 * la partición humana; la página no participa. Sin sesión el puente para y la
 * credencial se conserva sellada; la misma persona arranca sin código; otra
 * persona ve «emparejada por otra persona» sin que se le revele quién.
 */
import { describe, expect, it, vi } from "vitest";

import { CredentialStore, type Cipher, type FileStore } from "../src/credential-store.js";
import { SessionGate, type Whoami } from "../src/session-gate.js";

const cipher: Cipher = {
  isAvailable: () => true,
  encrypt: (t) => Buffer.from(t, "utf8").reverse(),
  decrypt: (b) => Buffer.from(b).reverse().toString("utf8"),
};
function file(): FileStore {
  let bytes: Buffer | null = null;
  return { read: () => bytes, write: (b) => (bytes = Buffer.from(b)), remove: () => (bytes = null) };
}
const cred = {
  deviceId: "dev-1",
  token: "t",
  generation: 1,
  expiresAt: "2026-09-10T10:00:00Z",
  partnerSlug: "p",
  displayName: "Mac",
};

function gate(whoami: Whoami, seed: Record<string, typeof cred> = {}) {
  const store = new CredentialStore(cipher, file());
  for (const [user, c] of Object.entries(seed)) store.put(user, c);
  const client = { whoami: vi.fn(async () => whoami) };
  return { gate: new SessionGate({ whoami: client, store }), client, store };
}

describe("qué decide la puerta", () => {
  it("sin sesión → para, y no ofrece emparejar (2.4, 11.1)", async () => {
    const { gate: g } = gate({ kind: "anonymous" }, { luis: cred });
    expect(await g.evaluate()).toEqual({ kind: "stop", reason: "anonymous" });
  });

  it("sesión sin pertenencia → para, y tampoco ofrece emparejar (2.4)", async () => {
    const { gate: g } = gate({ kind: "no_membership" });
    expect(await g.evaluate()).toEqual({ kind: "stop", reason: "no_membership" });
  });

  it("la misma persona que emparejó → arranca con su credencial, sin código (11.1)", async () => {
    const { gate: g } = gate({ kind: "member", userId: "luis", partnerSlug: "p" }, { luis: cred });
    expect(await g.evaluate()).toEqual({ kind: "start", userId: "luis", credential: cred });
  });

  it("el idioma de la cuenta viaja con la decisión, para que la barra hable como la consola", async () => {
    const { gate: g } = gate({ kind: "member", userId: "luis", partnerSlug: "p", locale: "es" }, { luis: cred });
    expect(await g.evaluate()).toMatchObject({ kind: "start", locale: "es" });
  });

  it("una persona sin credencial en una máquina sin nadie → emparejar, sin «otra persona»", async () => {
    const { gate: g } = gate({ kind: "member", userId: "luis", partnerSlug: "p" });
    expect(await g.evaluate()).toEqual({ kind: "pair_needed", userId: "luis", pairedByOther: false });
  });

  it("otra persona con sesión en una máquina emparejada por Luis → oferta, sin revelar a Luis", async () => {
    const { gate: g } = gate({ kind: "member", userId: "daniela", partnerSlug: "p" }, { luis: cred });
    const decision = await g.evaluate();
    expect(decision).toEqual({ kind: "pair_needed", userId: "daniela", pairedByOther: true });
    expect(JSON.stringify(decision)).not.toContain("luis");
  });

  it("la credencial se conserva sellada mientras la sesión está fuera", async () => {
    const { gate: g, store } = gate({ kind: "anonymous" }, { luis: cred });
    await g.evaluate();
    expect(store.get("luis")).toEqual(cred);
  });
});

describe("reacciona al cambio de cookie (2.2)", () => {
  it("cada cambio de la cookie de sesión vuelve a preguntar", async () => {
    const { gate: g, client } = gate({ kind: "anonymous" });
    const handlers: Array<() => void> = [];
    g.watch({ onSessionCookieChanged: (cb) => handlers.push(cb) });
    expect(client.whoami).toHaveBeenCalledTimes(0);
    handlers[0]!();
    handlers[0]!();
    await new Promise((r) => setTimeout(r, 0));
    expect(client.whoami).toHaveBeenCalledTimes(2);
  });

  it("la caducidad de la sesión es un cierre de sesión: mismo camino", async () => {
    const { gate: g } = gate({ kind: "anonymous" }, { luis: cred });
    const decision = await g.evaluate();
    expect(decision.kind).toBe("stop");
  });
});
