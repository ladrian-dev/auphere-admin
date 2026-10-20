import { Platform, type TextStyle } from "react-native";

import { tokens } from "./tokens.gen";

/**
 * Type, on the system font (plan: «tipografía del sistema»), at the console's
 * sizes. Every style scales with the phone's text size (`allowFontScaling` is
 * on by default and never turned off, R14.4): no fixed heights around text.
 */
const t = tokens.text;
const weight = (w: TextStyle["fontWeight"]): TextStyle => ({ fontWeight: w });

export const type = {
  largeTitle: { fontSize: t["2xl"], lineHeight: t["2xl"] * 1.15, ...weight("700"), letterSpacing: Platform.OS === "ios" ? 0.2 : 0 },
  title: { fontSize: t.xl, lineHeight: t.xl * 1.2, ...weight("700") },
  headline: { fontSize: t.md, lineHeight: t.md * 1.3, ...weight("600") },
  body: { fontSize: t.base, lineHeight: t.base * 1.45, ...weight("400") },
  bodyStrong: { fontSize: t.base, lineHeight: t.base * 1.45, ...weight("600") },
  callout: { fontSize: t.sm + 1, lineHeight: (t.sm + 1) * 1.4, ...weight("400") },
  subhead: { fontSize: t.sm, lineHeight: t.sm * 1.4, ...weight("500") },
  footnote: { fontSize: t.sm - 1, lineHeight: (t.sm - 1) * 1.4, ...weight("400") },
  caption: { fontSize: t.xs, lineHeight: t.xs * 1.4, ...weight("500") },
  figure: { fontSize: t["2xl"], lineHeight: t["2xl"] * 1.1, ...weight("700"), fontVariant: ["tabular-nums"] },
} satisfies Record<string, TextStyle>;

export type TypeName = keyof typeof type;
