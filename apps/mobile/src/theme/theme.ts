import { Platform, useColorScheme } from "react-native";

import { tokens, type Palette } from "./tokens.gen";

/**
 * The app's theme (spec 031, R14.3, D15): the console's roles, converted to
 * hex by `scripts/gen-tokens.mts`, following the phone's light or dark mode.
 * Components ask for a role (`colors.primaryText`), never for a colour.
 */
export type Scheme = "light" | "dark";

export type Theme = {
  scheme: Scheme;
  colors: Palette;
  /** The channels' logo colours (spec 069, D2): brand marks, per scheme, never theme roles. */
  brand: (typeof tokens.brand)[Scheme];
  radius: typeof tokens.radius;
  /** The 4 px grid. `space(4)` = 16. */
  space: (steps: number) => number;
};

const space = (steps: number) => steps * 4;

export function themeFor(scheme: Scheme): Theme {
  return { scheme, colors: tokens[scheme], brand: tokens.brand[scheme], radius: tokens.radius, space };
}

export function useTheme(): Theme {
  return themeFor(useColorScheme() === "dark" ? "dark" : "light");
}

/** Minimum touch target (R14.5): 44 pt on iOS, 48 dp on Android. One number keeps both. */
export const TOUCH = 48;

/** The platform's own minimum (spec 069, R3.3): 44 pt on iOS, 48 dp on Android. */
export const MIN_TARGET = Platform.OS === "android" ? 48 : 44;

/** The slop that takes a control `height` tall to the minimum target, split above and below (review H21). */
export function slopFor(height: number, target: number = MIN_TARGET): { top: number; bottom: number } {
  const s = Math.max(0, Math.ceil((target - height) / 2));
  return { top: s, bottom: s };
}

/** The top corners of a sheet rising from the bottom, from the scale: one value for every sheet. */
export const SHEET_RADIUS = tokens.radius.md * 2;

/**
 * The app's one radius scale (spec 069, D4, R1.10): the design's concentric
 * corners. App-only on purpose — the console's scale stops at 8, and
 * `tokens.gen.ts` is compared byte for byte with its source.
 */
export const RADII = { sm: 8, md: 12, lg: 16, xl: 20, sheet: 28, pill: 999 } as const;

/** Cards and grouped lists (spec 042 D12, 069 D4): one radius for every raised surface. */
export const CARD_RADIUS = RADII.lg;

/** The radius of what sits inside a rounded surface, so the corners stay concentric. Never below 4. */
export function concentric(outer: number, padding: number): number {
  return Math.max(outer - padding, 4);
}
