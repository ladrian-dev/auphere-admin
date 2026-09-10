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

/** Ejecuta lo que la política decidió. No decide nada por su cuenta. */
export function applyNotificationEffects(
  effects: Effect[],
  onClick: (actionId: string | null) => void,
): void {
  for (const effect of effects) {
    if (effect.kind === "notify" && Notification.isSupported()) {
      const notification = new Notification({ title: effect.title, body: effect.body });
      notification.on("click", () => onClick(effect.actionId));
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
