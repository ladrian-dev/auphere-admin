import { readFileSync } from "node:fs";
import { join } from "node:path";

import { formatHex, formatHex8, parse, toGamut, type Color } from "culori";

import { BANNER, emit } from "./_write.mts";

/**
 * Spec 031, D15: the app's colours are the console's, converted. The source
 * of truth is `packages/ui/src/styles/tokens.css` (OKLCH); this resolves every
 * `var()` the way the browser does on <html> — the @theme block, then the
 * light bridge (`:root`), then the dark one (`[data-theme="dark"]`) on top —
 * mixes `color-mix(... transparent)` into an alpha, maps to sRGB and writes hex.
 *
 * Only the roles the app uses leave this file: a component asks for
 * `colors.primaryText`, never for a brand swatch.
 */
const root = join(import.meta.dirname, "..");
const css = readFileSync(join(root, "../../packages/ui/src/styles/tokens.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(selector: RegExp): Record<string, string> {
  const m = selector.exec(css);
  if (!m) throw new Error(`tokens.css: no block ${selector}`);
  let depth = 1;
  let i = m.index + m[0].length;
  const start = i;
  while (depth > 0 && i < css.length) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") depth -= 1;
    i += 1;
  }
  const body = css.slice(start, i - 1);
  const vars: Record<string, string> = {};
  for (const decl of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[decl[1]!] = decl[2]!.trim();
  return vars;
}

const theme = block(/@theme\s*\{/);
const light = { ...theme, ...block(/:root\s*\{/) };
const dark = { ...light, ...block(/\[data-theme="dark"\]\s*\{/) };

function resolve(value: string, vars: Record<string, string>, seen: string[] = []): string {
  return value.replace(/var\((--[\w-]+)(?:\s*,\s*([^)]+))?\)/g, (_all, name: string, fallback?: string) => {
    if (seen.includes(name)) throw new Error(`tokens.css: circular var ${[...seen, name].join(" → ")}`);
    const next = vars[name] ?? fallback;
    if (next === undefined) throw new Error(`tokens.css: ${name} is not defined`);
    return resolve(next, vars, [...seen, name]);
  });
}

const gamut = toGamut("rgb", "oklch");

function color(value: string): Color {
  const mix = /^color-mix\(in oklab,\s*(.+?)\s+(\d+(?:\.\d+)?)%,\s*transparent\)$/.exec(value);
  if (mix) {
    const base = color(mix[1]!);
    return { ...base, alpha: (base.alpha ?? 1) * (Number(mix[2]) / 100) };
  }
  const parsed = parse(value);
  if (!parsed) throw new Error(`tokens.css: cannot parse colour «${value}»`);
  return parsed;
}

function hex(value: string): string {
  const c = gamut(color(value));
  const alpha = c.alpha ?? 1;
  return (alpha < 1 ? formatHex8(c) : formatHex(c)).toUpperCase();
}

/** App role → the CSS variable it reads. Same names as the console's Tailwind roles. */
const ROLES = {
  background: "--background",
  foreground: "--foreground",
  card: "--card",
  cardForeground: "--card-foreground",
  primary: "--primary",
  primaryForeground: "--primary-foreground",
  primaryText: "--color-primary-text",
  primaryDeep: "--color-primary-deep",
  secondary: "--secondary",
  muted: "--muted",
  mutedForeground: "--muted-foreground",
  subtle: "--color-fg-subtle",
  accent: "--accent",
  accentForeground: "--accent-foreground",
  accentSoft: "--color-accent-soft",
  accentDeep: "--color-accent-deep",
  destructive: "--destructive",
  warning: "--warning",
  border: "--border",
  borderSoft: "--color-border-soft",
  input: "--input",
  ring: "--ring",
  scrim: "--color-scrim",
  positive: "--color-status-positive",
  positiveText: "--color-status-positive-text",
  positiveBg: "--color-status-positive-bg",
  warningSolid: "--color-status-warning",
  warningText: "--color-status-warning-text",
  warningBg: "--color-status-warning-bg",
  danger: "--color-status-danger",
  dangerText: "--color-status-danger-text",
  dangerBg: "--color-status-danger-bg",
  info: "--color-status-info",
  infoText: "--color-status-info-text",
  infoBg: "--color-status-info-bg",
  /** The brand's dark green: the ground of the app icon (iOS and Android adaptive). */
  brandGround: "--color-dark-green",
} as const;

function palette(vars: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(ROLES).map(([role, name]) => {
      const raw = vars[name];
      if (raw === undefined) throw new Error(`tokens.css: ${name} is not defined`);
      return [role, hex(resolve(raw, vars))];
    }),
  );
}

function px(name: string): number {
  const raw = theme[name];
  const m = raw ? /^(\d+(?:\.\d+)?)(px|ms)$/.exec(raw) : null;
  if (!m) throw new Error(`tokens.css: ${name} is not a px/ms value`);
  return Number(m[1]);
}

const out = {
  light: palette(light),
  dark: palette(dark),
  radius: { sm: px("--radius-sm"), md: px("--radius-md"), full: px("--radius-full") },
  text: {
    xs: px("--text-xs"),
    sm: px("--text-sm"),
    base: px("--text-base"),
    md: px("--text-md"),
    lg: px("--text-lg"),
    xl: px("--text-xl"),
    "2xl": px("--text-2xl"),
  },
  duration: {
    instant: px("--duration-instant"),
    exit: px("--duration-exit"),
    fast: px("--duration-fast"),
    enter: px("--duration-enter"),
    state: px("--duration-state"),
  },
};

emit(
  join(root, "src/theme/tokens.gen.ts"),
  `${BANNER}// Source: packages/ui/src/styles/tokens.css · generator: scripts/gen-tokens.ts\n\n` +
    `export const tokens = ${JSON.stringify(out, null, 2)} as const;\n\n` +
    `export type Palette = { readonly [K in keyof typeof tokens.light]: string };\n`,
);
