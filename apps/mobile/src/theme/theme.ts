import { useColorScheme } from "react-native";

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
  radius: typeof tokens.radius;
  /** The 4 px grid. `space(4)` = 16. */
  space: (steps: number) => number;
};

const space = (steps: number) => steps * 4;

export function themeFor(scheme: Scheme): Theme {
  return { scheme, colors: tokens[scheme], radius: tokens.radius, space };
}

export function useTheme(): Theme {
  return themeFor(useColorScheme() === "dark" ? "dark" : "light");
}

/** Minimum touch target (R14.5): 44 pt on iOS, 48 dp on Android. One number keeps both. */
export const TOUCH = 48;

/** The top corners of a sheet rising from the bottom, from the scale: one value for every sheet. */
export const SHEET_RADIUS = tokens.radius.md * 2;

/**
 * Cards and grouped lists (spec 042, D12): one radius for every raised
 * surface. App-only on purpose — the console's scale stops at 8, and
 * `tokens.gen.ts` is compared byte for byte with its source.
 */
export const CARD_RADIUS = 12;

/** The radius of what sits inside a rounded surface, so the corners stay concentric. Never below 4. */
export function concentric(outer: number, padding: number): number {
  return Math.max(outer - padding, 4);
}
