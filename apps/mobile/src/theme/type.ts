import { Platform, type TextStyle } from "react-native";

import { tokens } from "./tokens.gen";

/**
 * Type, on the system font, in each platform's own scale (spec 042, R7.3,
 * R7.4, D12; contracts/ui.md §2): on iOS the sizes of the system's text
 * styles, so the app's text sits next to the system's bars and sheets as an
 * equal; on Android the console's tokens. No `letterSpacing` anywhere — the
 * system font already carries its own. Every style scales with the phone's
 * text size (`allowFontScaling` is on by default and never turned off, 031
 * R14.4): no fixed heights around text.
 */
export type TypeName = "largeTitle" | "title" | "headline" | "body" | "bodyStrong" | "callout" | "subhead" | "footnote" | "caption" | "figure";
type Scale = Record<TypeName, TextStyle>;

const weight = (w: TextStyle["fontWeight"]): TextStyle => ({ fontWeight: w });

/** iOS: the system's text styles (Large Title, Title 2, Headline, Body, Callout, Subheadline, Footnote, Caption 1) and Title 1 for figures. */
const ios: Scale = {
  largeTitle: { fontSize: 34, lineHeight: 41, ...weight("700") },
  title: { fontSize: 22, lineHeight: 28, ...weight("700") },
  headline: { fontSize: 17, lineHeight: 22, ...weight("600") },
  body: { fontSize: 17, lineHeight: 22, ...weight("400") },
  bodyStrong: { fontSize: 17, lineHeight: 22, ...weight("600") },
  callout: { fontSize: 16, lineHeight: 21, ...weight("400") },
  subhead: { fontSize: 15, lineHeight: 20, ...weight("500") },
  footnote: { fontSize: 13, lineHeight: 18, ...weight("400") },
  caption: { fontSize: 12, lineHeight: 16, ...weight("500") },
  figure: { fontSize: 28, lineHeight: 34, ...weight("700"), fontVariant: ["tabular-nums"] },
};

/** Android: the console's scale, from the tokens. */
const t = tokens.text;
const android: Scale = {
  largeTitle: { fontSize: t["2xl"], lineHeight: t["2xl"] * 1.15, ...weight("700") },
  title: { fontSize: t.xl, lineHeight: t.xl * 1.2, ...weight("700") },
  headline: { fontSize: t.md, lineHeight: t.md * 1.3, ...weight("600") },
  body: { fontSize: t.base, lineHeight: t.base * 1.45, ...weight("400") },
  bodyStrong: { fontSize: t.base, lineHeight: t.base * 1.45, ...weight("600") },
  callout: { fontSize: t.sm + 1, lineHeight: (t.sm + 1) * 1.4, ...weight("400") },
  subhead: { fontSize: t.sm, lineHeight: t.sm * 1.4, ...weight("500") },
  footnote: { fontSize: t.sm - 1, lineHeight: (t.sm - 1) * 1.4, ...weight("400") },
  caption: { fontSize: t.xs, lineHeight: t.xs * 1.4, ...weight("500") },
  figure: { fontSize: t["2xl"], lineHeight: t["2xl"] * 1.1, ...weight("700"), fontVariant: ["tabular-nums"] },
};

export const type: Scale = Platform.OS === "ios" ? ios : android;

/**
 * How far each iOS style may grow with the phone's text size: its size at
 * Apple's largest accessibility step (AX5) over its default. React Native
 * scales every style by the same factor (the body's), which at AX5 would put
 * a 22 pt title at 69 pt, past the 60 pt large title; Apple's own table keeps
 * the hierarchy (spec 042, R4.6, H8). Goes in as `maxFontSizeMultiplier`.
 */
const AX5: Record<TypeName, number> = {
  largeTitle: 60,
  title: 43,
  headline: 53,
  body: 53,
  bodyStrong: 53,
  callout: 51,
  subhead: 49,
  footnote: 44,
  caption: 43,
  figure: 44,
};
export const maxScale: Record<TypeName, number> = Object.fromEntries(
  (Object.keys(AX5) as TypeName[]).map((k) => [k, AX5[k] / ios[k].fontSize!]),
) as Record<TypeName, number>;

/**
 * Apple's Dynamic Type sizes for the large title the native bar draws (HIG
 * «Typography»), keyed by the body's own scale factor — which is what
 * `useWindowDimensions().fontScale` reports. The bar loses the system's
 * scaling the moment a colour is set on its title (react-native-screens then
 * draws it with a plain font), so the size goes in by hand, and the large
 * title never ends up smaller than the body under it (spec 042, R4.6, H8).
 * The inline title is not here on purpose: Apple keeps it fixed, the bar
 * cannot grow. Between two steps the size is interpolated; beyond the ends
 * it is held.
 */
const STEPS = [0.82, 0.88, 0.94, 1, 1.12, 1.24, 1.35, 1.65, 1.94, 2.35, 2.76, 3.12];
const HEADER_SIZES = {
  largeTitle: [31, 32, 33, 34, 36, 38, 40, 44, 48, 52, 56, 60],
};
export function headerSize(style: keyof typeof HEADER_SIZES, fontScale: number): number {
  const sizes = HEADER_SIZES[style];
  if (fontScale <= STEPS[0]!) return sizes[0]!;
  for (let i = 1; i < STEPS.length; i++) {
    const hi = STEPS[i]!;
    if (fontScale <= hi) {
      const lo = STEPS[i - 1]!;
      const t = (fontScale - lo) / (hi - lo);
      return Math.round(sizes[i - 1]! + (sizes[i]! - sizes[i - 1]!) * t);
    }
  }
  return sizes[sizes.length - 1]!;
}
