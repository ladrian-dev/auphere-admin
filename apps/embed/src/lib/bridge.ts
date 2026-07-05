/**
 * Iframe-side postMessage bridge (ADR-028).
 *
 * Counterpart of the loader's bridge in `@auphere/embed`. Security
 * invariants on THIS side:
 *
 *  - Incoming messages are accepted only from `window.parent` AND only
 *    when `event.origin` is in the session token's `allowed_origins`
 *    claim. Before init we accept the FIRST well-formed `auph:init` and
 *    then pin its origin — the token inside it is what authorises
 *    everything, and every API call re-validates it server-side.
 *  - Outgoing messages always target the pinned parent origin, never `*`.
 *  - The session token lives in module memory only — no cookies, no
 *    storage. A hard refresh simply re-runs the handshake.
 */

export interface Appearance {
  colorPrimary?: string;
  radius?: string;
  theme?: "light" | "dark";
}

export interface Recipient {
  phone: string;
  variables?: Record<string, string>;
}

export interface InitPayload {
  mode: "broadcast" | "signup";
  token: string;
  appearance: Appearance;
  locale: string;
  recipients: Recipient[];
}

type Listener = {
  onInit: (payload: InitPayload) => void;
  onToken: (token: string) => void;
  onClose?: () => void;
};

let parentOrigin: string | null = null;
let sessionToken: string | null = null;
let allowedOrigins: string[] = [];

/** Current session token for API calls (memory only). */
export function getToken(): string | null {
  return sessionToken;
}

function decodeAllowedOrigins(token: string): string[] {
  // Payload decode WITHOUT signature verification — fine here: this is
  // only used to validate the embedding origin for postMessage. The API
  // verifies the signature on every request; a forged token gets 401s
  // and an inert modal.
  try {
    const payload = token.split(".")[1] ?? "";
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return Array.isArray(decoded.allowed_origins)
      ? decoded.allowed_origins.filter((o: unknown): o is string => typeof o === "string")
      : [];
  } catch {
    return [];
  }
}

export function connectBridge(listener: Listener): () => void {
  function handleMessage(event: MessageEvent): void {
    if (event.source !== window.parent) return;
    const data = event.data as { type?: unknown } | null;
    if (!data || typeof data.type !== "string") return;

    if (data.type === "auph:init" && parentOrigin === null) {
      const payload = data as unknown as InitPayload & { type: string };
      if (typeof payload.token !== "string" || !payload.token) return;
      const origins = decodeAllowedOrigins(payload.token);
      // Empty allow-list = key not configured yet → accept any origin in
      // dev ONLY; in prod an empty list rejects.
      const originOk =
        origins.includes(event.origin) ||
        (origins.length === 0 && process.env.NODE_ENV !== "production");
      if (!originOk) {
        // Log-and-drop: a hostile embedder gets silence, not an oracle.
        console.warn("[auphere-embed] init from non-allowed origin dropped", event.origin);
        return;
      }
      parentOrigin = event.origin;
      allowedOrigins = origins;
      sessionToken = payload.token;
      listener.onInit(payload);
      return;
    }

    // Post-init messages must come from the pinned origin.
    if (parentOrigin === null || event.origin !== parentOrigin) return;

    if (data.type === "auph:token") {
      const token = (data as { token?: unknown }).token;
      if (typeof token === "string" && token) {
        sessionToken = token;
        listener.onToken(token);
      }
    } else if (data.type === "auph:close") {
      listener.onClose?.();
    }
  }

  window.addEventListener("message", handleMessage);
  return () => window.removeEventListener("message", handleMessage);
}

/** Send a namespaced message to the embedding page. */
export function postToParent(type: string, payload: Record<string, unknown> = {}): void {
  if (parentOrigin === null) return; // never before the origin is pinned
  window.parent.postMessage({ type, ...payload }, parentOrigin);
}

/** Announce readiness — the ONE message sent before the origin is pinned.
 * `targetOrigin: "*"` carries no data beyond "the modal booted". */
export function announceReady(): void {
  window.parent.postMessage({ type: "auph:ready" }, "*");
}

export function getAllowedOrigins(): string[] {
  return allowedOrigins;
}
