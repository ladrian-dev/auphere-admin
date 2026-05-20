/**
 * WhatsApp Cloud API visual tokens.
 *
 * Goal: produce a static preview that looks unmistakably like a real
 * WhatsApp business chat bubble so the operator can spot rendering
 * regressions ("does the agent's reply look right?") before they ship.
 * Not pixel-perfect — we deliberately keep this as a HAND-DRAWN mock,
 * not a screenshot of the real client, so changes are diff-readable.
 */
import type { CSSProperties } from "react";

export const wa = {
  bubble: "#d9fdd3",       // outgoing (from the business) — pale green
  text: "#111b21",
  textMuted: "#667781",
  border: "#cdebc4",
  link: "#1baadb",
  buttonText: "#1baadb",
  divider: "#e9edef",
  surface: "#ffffff",
  surfaceMuted: "#f0f2f5",
  // WhatsApp wallpaper-like background; the gallery shows it behind the
  // bubble so the preview reads as a chat, not a card on white.
  chatBg: "#e5ddd5",
  radius: 8,
  spacing: 8,
} as const;

export const phoneFrame: CSSProperties = {
  width: 340,
  background: wa.chatBg,
  borderRadius: 22,
  padding: 14,
  fontFamily:
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  fontSize: 14,
  color: wa.text,
  // Subtle inner shadow so the bubbles read as "inside" the phone.
  boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.04)",
};

export const bubble: CSSProperties = {
  background: wa.bubble,
  borderRadius: wa.radius,
  padding: "6px 8px 8px",
  maxWidth: 280,
  marginLeft: "auto",  // outgoing — right-aligned
  position: "relative",
  // Tail indicator (the WhatsApp "speech triangle") drawn with a clip-path
  // would distract from snapshot diffs; we skip it on purpose.
  lineHeight: 1.36,
  wordBreak: "break-word",
};

export const button: CSSProperties = {
  display: "block",
  width: "100%",
  padding: "8px 0",
  textAlign: "center",
  color: wa.buttonText,
  background: "transparent",
  border: "none",
  borderTop: `1px solid ${wa.divider}`,
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 500,
};

export const meta: CSSProperties = {
  fontSize: 11,
  color: wa.textMuted,
  marginTop: 4,
  textAlign: "right",
};
