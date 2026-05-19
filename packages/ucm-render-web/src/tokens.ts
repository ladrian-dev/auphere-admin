/**
 * Style tokens — kept inline (no CSS-in-JS lib) so the package has zero
 * runtime dependencies beyond React. The QA Playground host owns the
 * theming layer; these defaults exist so the components render
 * reasonably in isolation (gallery, snapshot tests).
 *
 * Customising the look is done by overriding the React tree from the
 * outside; the components do not read any CSS variable so they're
 * resilient to host token systems that change names.
 */
import type { CSSProperties } from "react";

export const tokens = {
  surface: "#ffffff",
  surfaceMuted: "#f5f5f5",
  border: "#e3e3e3",
  text: "#111111",
  textMuted: "#666666",
  accent: "#2d6cdf",
  accentText: "#ffffff",
  danger: "#c0392b",
  radius: 12,
  radiusSm: 8,
  spacing: 8,
} as const;

export const bubble: CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: tokens.radius,
  padding: `${tokens.spacing * 1.5}px ${tokens.spacing * 1.75}px`,
  color: tokens.text,
  fontSize: 14,
  lineHeight: 1.45,
  maxWidth: 540,
};

export const button: CSSProperties = {
  appearance: "none",
  border: `1px solid ${tokens.accent}`,
  background: tokens.surface,
  color: tokens.accent,
  borderRadius: 999,
  padding: "8px 14px",
  fontSize: 14,
  fontWeight: 500,
  cursor: "pointer",
  // Focus ring is provided via outlineWidth on :focus-visible — set via
  // the global stylesheet in the host. Without that, we still keep the
  // browser default outline (do NOT remove it).
};

export const primaryButton: CSSProperties = {
  ...button,
  background: tokens.accent,
  color: tokens.accentText,
};

export const fallbackBox: CSSProperties = {
  ...bubble,
  background: "#fff8e1",
  borderColor: "#f0d066",
  fontSize: 13,
  color: tokens.textMuted,
};
