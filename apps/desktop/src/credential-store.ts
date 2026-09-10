/**
 * El almacén de la credencial de máquina — Requisitos 1.2 y 14.2 (spec 002).
 *
 * **Cifrada con el llavero del sistema, por persona, nunca en claro.** El cifrado
 * y el fichero se inyectan: en producción son `safeStorage` de Electron y un
 * fichero en `userData`; en los tests, dobles que sí transforman los bytes, para
 * que «nunca texto plano» sea una afirmación y no una esperanza.
 *
 * Sin cifrado disponible **no se escribe nada** y la barra lo dice: guardar en
 * claro «mientras tanto» es exactamente la llave en el disco de otra persona que
 * el Requisito 15.2 de la 001 prohíbe.
 */

export type StoredCredential = {
  deviceId: string;
  token: string;
  generation: number;
  expiresAt: string;
  partnerSlug: string;
  displayName: string;
};

export interface Cipher {
  isAvailable(): boolean;
  encrypt(text: string): Buffer;
  decrypt(bytes: Buffer): string;
}

export interface FileStore {
  read(): Buffer | null;
  write(bytes: Buffer): void;
  remove(): void;
}

export class EncryptionUnavailable extends Error {
  constructor() {
    super("el sistema no ofrece cifrado para guardar la credencial: no se guarda");
    this.name = "EncryptionUnavailable";
  }
}

type Vault = Record<string, StoredCredential>;

export class CredentialStore {
  private vault: Vault;

  constructor(
    private readonly cipher: Cipher,
    private readonly file: FileStore,
  ) {
    this.vault = this.load();
  }

  get encryptionAvailable(): boolean {
    return this.cipher.isAvailable();
  }

  users(): string[] {
    return Object.keys(this.vault);
  }

  get(userId: string): StoredCredential | undefined {
    return this.vault[userId];
  }

  put(userId: string, credential: StoredCredential): void {
    if (!this.cipher.isAvailable()) throw new EncryptionUnavailable();
    this.vault = { ...this.vault, [userId]: credential };
    this.persist();
  }

  /** Desemparejar: la entrada desaparece y el fichero se sobrescribe entero. */
  forget(userId: string): void {
    const { [userId]: _gone, ...rest } = this.vault;
    this.vault = rest;
    if (Object.keys(rest).length === 0) {
      this.file.remove();
      return;
    }
    this.persist();
  }

  private persist(): void {
    this.file.write(this.cipher.encrypt(JSON.stringify(this.vault)));
  }

  private load(): Vault {
    const bytes = this.file.read();
    if (bytes === null || !this.cipher.isAvailable()) return {};
    try {
      const parsed: unknown = JSON.parse(this.cipher.decrypt(bytes));
      return isVault(parsed) ? parsed : {};
    } catch {
      // Un fichero corrupto no rompe la app: se trata como vacío y se volverá a emparejar.
      return {};
    }
  }
}

function isVault(value: unknown): value is Vault {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.values(value as Record<string, unknown>).every(
    (v) =>
      typeof v === "object" &&
      v !== null &&
      typeof (v as StoredCredential).deviceId === "string" &&
      typeof (v as StoredCredential).token === "string",
  );
}
