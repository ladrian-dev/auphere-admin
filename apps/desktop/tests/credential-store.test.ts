/**
 * Requisitos 1.2 y 14.2 — la credencial de máquina, cifrada y por persona.
 *
 * Nunca texto plano en disco; una entrada por `user_id`; sin cifrado disponible
 * **no se guarda nada**; desemparejar borra la entrada y sobrescribe el fichero.
 */
import { describe, expect, it } from "vitest";

import {
  CredentialStore,
  EncryptionUnavailable,
  type Cipher,
  type FileStore,
  type StoredCredential,
} from "../src/credential-store.js";

/** Un cifrado de mentira que sí transforma: invierte y desplaza cada byte. */
function fakeCipher(available = true): Cipher {
  return {
    isAvailable: () => available,
    encrypt: (text) => Buffer.from(Array.from(Buffer.from(text, "utf8")).reverse().map((b) => (b + 7) % 256)),
    decrypt: (buf) => Buffer.from(Array.from(buf).map((b) => (b + 256 - 7) % 256).reverse()).toString("utf8"),
  };
}

function memoryFile(): FileStore & { bytes: Buffer | null; writes: number } {
  const store = {
    bytes: null as Buffer | null,
    writes: 0,
    read: () => store.bytes,
    write: (buf: Buffer) => {
      store.bytes = Buffer.from(buf);
      store.writes += 1;
    },
    remove: () => {
      store.bytes = null;
    },
  };
  return store;
}

const cred = (n: string): StoredCredential => ({
  deviceId: `dev-${n}`,
  token: `eyJhbGciOi.${n}.firma`,
  generation: 1,
  expiresAt: "2026-09-10T10:00:00Z",
  partnerSlug: "nexus-retail",
  displayName: `Mac de ${n}`,
});

describe("nunca texto plano (14.2)", () => {
  it("lo que hay en disco no contiene el token ni su cabecera JWT", () => {
    const file = memoryFile();
    const store = new CredentialStore(fakeCipher(), file);
    store.put("luis", cred("luis"));
    const onDisk = file.bytes!.toString("latin1");
    expect(onDisk).not.toContain("eyJ");
    expect(onDisk).not.toContain("firma");
    expect(onDisk).not.toContain("dev-luis");
  });

  it("y se recupera entera al volver a abrir", () => {
    const file = memoryFile();
    new CredentialStore(fakeCipher(), file).put("luis", cred("luis"));
    const reopened = new CredentialStore(fakeCipher(), file);
    expect(reopened.get("luis")).toEqual(cred("luis"));
  });
});

describe("por persona (Historia 5)", () => {
  it("dos personas, dos entradas, y cada una la suya", () => {
    const store = new CredentialStore(fakeCipher(), memoryFile());
    store.put("luis", cred("luis"));
    store.put("daniela", cred("daniela"));
    expect(store.get("luis")?.deviceId).toBe("dev-luis");
    expect(store.get("daniela")?.deviceId).toBe("dev-daniela");
    expect(store.users().sort()).toEqual(["daniela", "luis"]);
  });

  it("desemparejar borra la entrada y sobrescribe el fichero", () => {
    const file = memoryFile();
    const store = new CredentialStore(fakeCipher(), file);
    store.put("luis", cred("luis"));
    store.put("daniela", cred("daniela"));
    const writesBefore = file.writes;
    store.forget("luis");
    expect(file.writes).toBe(writesBefore + 1);
    expect(store.get("luis")).toBeUndefined();
    expect(new CredentialStore(fakeCipher(), file).get("daniela")?.deviceId).toBe("dev-daniela");
    expect(file.bytes!.toString("latin1")).not.toContain("luis");
  });
});

describe("sin cifrado disponible (1.2)", () => {
  it("no se escribe nada, y se dice", () => {
    const file = memoryFile();
    const store = new CredentialStore(fakeCipher(false), file);
    expect(store.encryptionAvailable).toBe(false);
    expect(() => store.put("luis", cred("luis"))).toThrow(EncryptionUnavailable);
    expect(file.bytes).toBeNull();
  });

  it("un fichero corrupto no rompe la app: se trata como vacío", () => {
    const file = memoryFile();
    file.bytes = Buffer.from("basura");
    const store = new CredentialStore(fakeCipher(), file);
    expect(store.users()).toEqual([]);
  });
});
