/**
 * Fullscreen iframe overlay lifecycle (ADR-028).
 *
 * The iframe cannot escape its own box, so the LOADER styles it to
 * cover the viewport (`position: fixed; inset: 0`) while it's open —
 * the "breakout" pattern used by Stripe Checkout and Plaid Link.
 * Scroll-lock + focus restore are handled here; the focus trap itself
 * lives inside the iframe document (it owns the focusable elements).
 *
 * Security invariants enforced in this file:
 *  - messages are only accepted from the configured embed origin AND
 *    from this exact iframe's contentWindow;
 *  - outgoing messages always use an explicit `targetOrigin` (never `*`);
 *  - the session token travels ONLY via postMessage — never in the URL.
 */

import { MSG } from "./constants";

type MessageHandler = (type: string, payload: Record<string, unknown>) => void;

export interface OverlayHandle {
  post(type: string, payload?: Record<string, unknown>): void;
  close(): void;
}

const OVERLAY_Z = 2147483646; // one below max — leaves room for the host's own emergency layers

export function openOverlay(options: {
  url: string;
  embedOrigin: string;
  title: string;
  onMessage: MessageHandler;
  onClose: () => void;
}): OverlayHandle {
  const { url, embedOrigin, title, onMessage, onClose } = options;

  const previousFocus =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const previousOverflow = document.body.style.overflow;

  const backdrop = document.createElement("div");
  backdrop.setAttribute("data-auphere-embed", "");
  backdrop.style.cssText = [
    "position:fixed",
    "inset:0",
    `z-index:${OVERLAY_Z}`,
    "background:rgba(0,0,0,0.45)",
    "opacity:0",
    "transition:opacity 200ms ease",
  ].join(";");

  const iframe = document.createElement("iframe");
  iframe.src = url;
  iframe.title = title;
  iframe.setAttribute("role", "dialog");
  iframe.setAttribute("aria-modal", "true");
  iframe.allow = "clipboard-write";
  iframe.style.cssText = [
    "position:fixed",
    "inset:0",
    "width:100%",
    "height:100%",
    "border:0",
    `z-index:${OVERLAY_Z + 1}`,
    "background:transparent",
    "color-scheme:normal",
  ].join(";");

  let closed = false;

  function handleMessage(event: MessageEvent): void {
    // Origin AND source must match — a message from another tab or a
    // nested frame on the same origin is not our modal.
    if (event.origin !== embedOrigin) return;
    if (event.source !== iframe.contentWindow) return;
    const data = event.data as { type?: unknown } | null;
    if (!data || typeof data.type !== "string" || !data.type.startsWith("auph:")) return;
    onMessage(data.type, data as Record<string, unknown>);
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") close();
  }

  function close(): void {
    if (closed) return;
    closed = true;
    window.removeEventListener("message", handleMessage);
    document.removeEventListener("keydown", handleKeydown);
    document.body.style.overflow = previousOverflow;
    backdrop.remove();
    iframe.remove();
    previousFocus?.focus?.();
    onClose();
  }

  window.addEventListener("message", handleMessage);
  document.addEventListener("keydown", handleKeydown);
  document.body.style.overflow = "hidden"; // scroll-lock while open
  document.body.append(backdrop, iframe);
  requestAnimationFrame(() => {
    backdrop.style.opacity = "1";
  });
  iframe.focus();

  return {
    post(type, payload = {}) {
      // Explicit targetOrigin — if the frame navigated elsewhere the
      // browser drops the message instead of leaking the token.
      iframe.contentWindow?.postMessage({ type, ...payload }, embedOrigin);
    },
    close,
  };
}

export { MSG };
