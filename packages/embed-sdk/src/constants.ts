/** Production embed origin. Overridable per-instance via `config.embedOrigin` (dev/staging). */
export const DEFAULT_EMBED_ORIGIN = "https://embed.auphere.com";

/** postMessage envelope namespace — every message is `{ type: "auph:…" }`. */
export const MSG = {
  // iframe → loader
  READY: "auph:ready",
  RESIZE: "auph:resize",
  CLOSE: "auph:close",
  STATUS: "auph:status",
  BROADCAST_DONE: "auph:broadcast:done",
  TOKEN_EXPIRING: "auph:token:expiring",
  CONNECTED: "auph:connected",
  ERROR: "auph:error",
  // loader → iframe
  INIT: "auph:init",
  TOKEN: "auph:token",
} as const;
