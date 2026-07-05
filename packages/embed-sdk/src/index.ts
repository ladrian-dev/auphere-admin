/**
 * `@auphere/embed` — public entrypoint (ADR-028).
 *
 * ```ts
 * import { createAuphere } from "@auphere/embed";
 *
 * const auphere = createAuphere({
 *   partnerSlug: "acme",
 *   fetchSession: async () => (await fetch("/api/auphere/session", { method: "POST" })).json(),
 * });
 *
 * await auphere.openBroadcast({ recipients: [{ phone: "+56912345678", variables: { cliente: "Ana" } }] });
 * ```
 */

import { DEFAULT_EMBED_ORIGIN, MSG } from "./constants";
import { openOverlay } from "./iframe-manager";
import type {
  Auphere,
  AuphereConfig,
  ConnectionStatus,
  ConnectWhatsAppOptions,
  OpenBroadcastOptions,
  WidgetSession,
  WidgetSessionWire,
} from "./types";

export type {
  Appearance,
  Auphere,
  AuphereConfig,
  BroadcastRecipient,
  ConnectionStatus,
  ConnectWhatsAppOptions,
  FetchSession,
  OpenBroadcastOptions,
  WidgetSession,
} from "./types";

function normalizeSession(raw: WidgetSession | WidgetSessionWire): WidgetSession {
  if ("sessionToken" in raw && typeof raw.sessionToken === "string") return raw;
  const wire = raw as WidgetSessionWire;
  return {
    sessionToken: wire.session_token,
    expiresIn: wire.expires_in,
    whatsapp: wire.whatsapp
      ? {
          status: wire.whatsapp.status,
          displayPhoneNumber: wire.whatsapp.display_phone_number ?? null,
        }
      : undefined,
  };
}

export function createAuphere(config: AuphereConfig): Auphere {
  if (typeof config?.fetchSession !== "function") {
    throw new Error("@auphere/embed: `fetchSession` is required");
  }
  if (!config.partnerSlug) {
    throw new Error("@auphere/embed: `partnerSlug` is required");
  }
  const embedOrigin = (config.embedOrigin ?? DEFAULT_EMBED_ORIGIN).replace(/\/+$/, "");

  let status: ConnectionStatus = "unknown";
  const listeners = new Set<(status: ConnectionStatus) => void>();
  let activeOverlay: { close(): void } | null = null;

  function setStatus(next: ConnectionStatus): void {
    if (next === status) return;
    status = next;
    listeners.forEach((listener) => listener(status));
  }

  async function mintSession(): Promise<WidgetSession> {
    const session = normalizeSession(await config.fetchSession());
    if (!session.sessionToken) {
      throw new Error("@auphere/embed: fetchSession returned no session token");
    }
    if (session.whatsapp?.status) setStatus(session.whatsapp.status);
    return session;
  }

  function iframeUrl(route: "broadcast" | "signup"): string {
    return `${embedOrigin}/${route}?p=${encodeURIComponent(config.partnerSlug)}`;
  }

  async function open(
    route: "broadcast" | "signup",
    handlers: {
      recipients?: OpenBroadcastOptions["recipients"];
      onDone?: OpenBroadcastOptions["onDone"];
      onConnected?: ConnectWhatsAppOptions["onConnected"];
      onExit?: () => void;
    },
  ): Promise<void> {
    if (activeOverlay) activeOverlay.close();
    const session = await mintSession(); // mint BEFORE mounting: fail fast, no empty modal

    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const overlay = openOverlay({
        url: iframeUrl(route),
        embedOrigin,
        title: route === "broadcast" ? "Auphere — Campañas WhatsApp" : "Auphere — Conectar WhatsApp",
        onClose: () => {
          activeOverlay = null;
          handlers.onExit?.();
          if (!settled) {
            settled = true;
            resolve();
          }
        },
        onMessage: (type, payload) => {
          switch (type) {
            case MSG.READY:
              overlay.post(MSG.INIT, {
                mode: route,
                token: session.sessionToken,
                appearance: config.appearance ?? {},
                locale: config.locale ?? document.documentElement.lang ?? "es",
                recipients: handlers.recipients ?? [],
              });
              if (!settled) {
                settled = true;
                resolve();
              }
              break;
            case MSG.TOKEN_EXPIRING:
              void mintSession()
                .then((fresh) => overlay.post(MSG.TOKEN, { token: fresh.sessionToken }))
                .catch(() => overlay.post(MSG.ERROR, { code: "token_refresh_failed" }));
              break;
            case MSG.STATUS: {
              const value = payload["whatsappConnected"];
              if (typeof value === "boolean") setStatus(value ? "connected" : "not_connected");
              break;
            }
            case MSG.BROADCAST_DONE:
              handlers.onDone?.({
                broadcastId: String(payload["broadcastId"] ?? ""),
                accepted: Number(payload["accepted"] ?? 0),
              });
              break;
            case MSG.CONNECTED:
              setStatus("connected");
              handlers.onConnected?.({
                displayPhoneNumber:
                  typeof payload["displayPhoneNumber"] === "string"
                    ? payload["displayPhoneNumber"]
                    : null,
              });
              break;
            case MSG.CLOSE:
              overlay.close();
              break;
            case MSG.ERROR:
              if (!settled) {
                settled = true;
                overlay.close();
                reject(new Error(`@auphere/embed: ${String(payload["code"] ?? "embed_error")}`));
              }
              break;
          }
        },
      });
      activeOverlay = overlay;
    });
  }

  return {
    getStatus: () => status,
    async refreshStatus() {
      await mintSession();
      return status;
    },
    onStatusChange(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    openBroadcast(options: OpenBroadcastOptions) {
      return open("broadcast", options);
    },
    connectWhatsApp(options: ConnectWhatsAppOptions = {}) {
      return open("signup", options);
    },
    destroy() {
      activeOverlay?.close();
      activeOverlay = null;
      listeners.clear();
    },
  };
}
