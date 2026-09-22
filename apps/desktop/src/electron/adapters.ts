/**
 * Los adaptadores de Electron para lo que el núcleo pide por interfaz.
 *
 * Todo lo que decide está en módulos puros con tests; aquí solo se conecta
 * cada interfaz a la API de Electron o de Node que la implementa. Sin tests
 * unitarios a propósito: probarlos con dobles solo demostraría que los dobles
 * hacen lo que les dijimos.
 */
import { accessSync, constants, existsSync, mkdirSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { Notification, app, dialog, safeStorage, session, shell, type BaseWindow } from "electron";

import type { Cipher, FileStore } from "../credential-store.js";
import type { DirectoryFs } from "../directory-declare.js";
import { type Effect, type Prefs, normalisePrefs } from "../notifications-policy.js";
import type { SessionCookieWatcher, Whoami, WhoamiClient } from "../session-gate.js";
import { HUMAN_PARTITION } from "../session-isolation.js";

// ── credencial: safeStorage + fichero en userData (D7) ──────────────────

export function safeStorageCipher(): Cipher {
  return {
    isAvailable: () => safeStorage.isEncryptionAvailable(),
    encrypt: (text) => safeStorage.encryptString(text),
    decrypt: (bytes) => safeStorage.decryptString(bytes),
  };
}

export function userDataFile(name = "credentials.bin"): FileStore {
  const path = join(app.getPath("userData"), name);
  return {
    read: () => (existsSync(path) ? readFileSync(path) : null),
    write: (bytes) => {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, bytes, { mode: 0o600 });
    },
    remove: () => rmSync(path, { force: true }),
  };
}

// ── quién está dentro: whoami con la cookie de la partición humana (D6) ─

export function consoleWhoami(consoleUrl: string): WhoamiClient {
  const origin = new URL(consoleUrl).origin;
  return {
    async whoami(): Promise<Whoami> {
      const response = await session.fromPartition(HUMAN_PARTITION).fetch(`${origin}/api/session/whoami`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      if (response.status === 401) return { kind: "anonymous" };
      if (response.status === 403) return { kind: "no_membership" };
      if (!response.ok) return { kind: "anonymous" };
      // Una respuesta que no es JSON (una página, un proxy) no es una persona.
      let body: { user_id?: string; partner_slug?: string; locale?: string; permissions?: unknown };
      try {
        body = (await response.json()) as typeof body;
      } catch {
        return { kind: "anonymous" };
      }
      if (!body.user_id) return { kind: "anonymous" };
      const locale = body.locale === "en" ? "en" : body.locale === "es" ? "es" : undefined;
      return {
        kind: "member",
        userId: String(body.user_id),
        partnerSlug: String(body.partner_slug ?? ""),
        ...(locale ? { locale } : {}),
        ...(Array.isArray(body.permissions)
          ? { permissions: body.permissions.filter((p): p is string => typeof p === "string") }
          : {}),
      };
    },
  };
}

// ── registrar la máquina con la sesión (spec 012, R3) ───────────────────

/** Lo que la aplicación sabe de sí misma y la persona no elige. */
export type MachineFacts = {
  hostname: string;
  platform: "macos" | "windows";
  installId: string;
  appVersion?: string;
};

/** Lo que el BFF devuelve, **una sola vez**. */
export type RegisteredMachine = {
  deviceId: string;
  credential: string;
  generation: number;
  expiresAt: string;
  partnerSlug: string;
  displayName: string;
};

export type RegisterOutcome =
  | { kind: "registered"; machine: RegisteredMachine }
  | { kind: "sign_in_again" }
  | { kind: "at_cap" }
  | { kind: "unavailable" };

/**
 * Registra esta máquina con la sesión que la aplicación ya tiene.
 *
 * Mismo camino que `consoleWhoami`: la cookie de la partición humana desde el
 * proceso principal. No hay código que teclear — para poder teclear el de antes,
 * la aplicación ya tenía esta misma sesión confirmada.
 *
 * Los tres rechazos se distinguen porque **llevan a cosas distintas**: entrar de
 * nuevo, retirar una máquina, o reintentar. Uniformarlos dejaría a la persona
 * sin saber qué hacer.
 */
export function registerMachineWithSession(consoleUrl: string) {
  const origin = new URL(consoleUrl).origin;
  return async function register(facts: MachineFacts): Promise<RegisterOutcome> {
    let response: Response;
    try {
      response = await session.fromPartition(HUMAN_PARTITION).fetch(`${origin}/api/desktop/register-machine`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          hostname: facts.hostname,
          platform: facts.platform,
          install_id: facts.installId,
          ...(facts.appVersion ? { app_version: facts.appVersion } : {}),
        }),
      });
    } catch {
      // Sin red no se decide nada: no es que la sesión sea vieja.
      return { kind: "unavailable" };
    }

    if (response.status === 401) return { kind: "sign_in_again" };
    if (response.status === 409) return { kind: "at_cap" };
    if (!response.ok) return { kind: "unavailable" };

    let body: {
      device_id?: string;
      credential?: string;
      generation?: number;
      expires_at?: string;
      partner_slug?: string;
      display_name?: string;
    };
    try {
      body = (await response.json()) as typeof body;
    } catch {
      return { kind: "unavailable" };
    }
    if (!body.device_id || !body.credential) return { kind: "unavailable" };

    return {
      kind: "registered",
      machine: {
        deviceId: String(body.device_id),
        credential: String(body.credential),
        generation: Number(body.generation ?? 1),
        expiresAt: String(body.expires_at ?? ""),
        partnerSlug: String(body.partner_slug ?? ""),
        displayName: String(body.display_name ?? facts.hostname),
      },
    };
  };
}

// ── avisos del sistema y preferencia (spec 003, R7) ─────────────────────

/** La preferencia vive en `userData`: es del ordenador, no de la cuenta. */
export function notificationPrefsStore(): { read(): Prefs; write(next: Prefs): Prefs } {
  const file = userDataFile("notifications.json");
  return {
    read(): Prefs {
      try {
        const raw = file.read();
        return normalisePrefs(raw ? (JSON.parse(raw.toString("utf8")) as Partial<Prefs>) : undefined);
      } catch {
        return normalisePrefs(undefined);
      }
    },
    write(next: Prefs): Prefs {
      const prefs = normalisePrefs(next);
      file.write(Buffer.from(JSON.stringify(prefs), "utf8"));
      return prefs;
    },
  };
}

/**
 * Ejecuta lo que la política decidió. No decide nada por su cuenta.
 *
 * `onShown` existe por R7.8: macOS no deja consultar si los avisos están
 * concedidos, así que lo único que se puede saber es si uno llegó a mostrarse.
 * Eso, y sólo eso, es lo que mueve el estado del permiso.
 */
export function applyNotificationEffects(
  effects: Effect[],
  onClick: (actionId: string | null) => void,
  onShown?: (shown: boolean) => void,
): void {
  for (const effect of effects) {
    if (effect.kind === "notify") {
      if (!Notification.isSupported()) {
        onShown?.(false);
        continue;
      }
      const notification = new Notification({ title: effect.title, body: effect.body });
      notification.on("click", () => onClick(effect.actionId));
      notification.on("failed", () => onShown?.(false));
      notification.on("show", () => onShown?.(true));
      notification.show();
    }
    if (effect.kind === "badge") {
      // En macOS es el punto del Dock; en Windows y Linux, lo que haya.
      app.setBadgeCount(effect.count);
    }
  }
}

/** El `fetch` de la partición de la persona, para el `PlatformClient` (spec 003, D9). */
export function partitionFetch(): (url: string, init?: RequestInit) => Promise<Response> {
  return (url, init) => session.fromPartition(HUMAN_PARTITION).fetch(url, init);
}

export const SESSION_COOKIE = "nexus-console.session";

export function sessionCookieWatcher(): SessionCookieWatcher {
  return {
    onSessionCookieChanged(callback) {
      session.fromPartition(HUMAN_PARTITION).cookies.on("changed", (_event, cookie) => {
        if (cookie.name === SESSION_COOKIE) callback();
      });
    },
  };
}

// ── directorio: selector nativo + comprobaciones del sistema (R7) ───────

export const nodeDirectoryFs: DirectoryFs = {
  exists: (p) => existsSync(p),
  isDirectory: (p) => {
    try {
      return statSync(p).isDirectory();
    } catch {
      return false;
    }
  },
  realpath: (p) => realpathSync.native(p),
  canRead: (p) => {
    try {
      accessSync(p, constants.R_OK | constants.X_OK);
      return true;
    } catch {
      return false;
    }
  },
};

export function nativeDirectoryPicker(window: BaseWindow, title: string): () => Promise<string | null> {
  return async () => {
    const result = await dialog.showOpenDialog(window, {
      title,
      properties: ["openDirectory", "createDirectory", "noResolveAliases"],
    });
    return result.canceled || result.filePaths.length === 0 ? null : (result.filePaths[0] ?? null);
  };
}

export function openExternal(url: string): Promise<void> {
  return shell.openExternal(url);
}


/**
 * El atajo global para traer la aplicación al frente (12.4).
 *
 * Vive en un fichero del directorio de datos y no en una pantalla: la spec 003
 * no tiene ajustes, e inventar una pantalla para un atajo sería añadir
 * superficie que nadie pidió. Lo que sí hace falta es que se pueda cambiar sin
 * recompilar, porque un atajo fijo choca con el de otra aplicación y entonces
 * no hay forma de arreglarlo.
 *
 * Un valor que no parece un acelerador de Electron se ignora: registrar basura
 * lanza, y arrancar es más importante que el atajo.
 */
export function readShortcut(fallback = "CommandOrControl+Shift+A"): string | null {
  const file = userDataFile("shortcut.json");
  try {
    const raw = file.read();
    if (!raw) return fallback;
    const parsed = JSON.parse(raw.toString("utf8")) as { accelerator?: unknown };
    const value = parsed.accelerator;
    if (value === null) return null; // apagarlo a propósito es una opción
    if (typeof value !== "string" || !/^[A-Za-z0-9+]+$/.test(value.replace(/\s/g, ""))) {
      return fallback;
    }
    return value;
  } catch {
    return fallback;
  }
}

/** El idioma de la cáscara para lo que se ve fuera de la ventana (bandeja). */
export function appLocale(): "es" | "en" {
  return (app.getLocale() || "es").toLowerCase().startsWith("en") ? "en" : "es";
}
