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

/**
 * Spec 069 (D2): roles only the app reads, for the design the owner approved
 * (selection in ink, the mint highlight, the agent's bubble, the inverted
 * toast). They are computed from the same CSS variables, so `tokens.css` and
 * the web stay as they are. `over(color, alpha, ground)` lays a colour at an
 * alpha over an opaque ground and gives the opaque result (the design's
 * `color-mix(hi 16%, surface)`), because a bubble must not let the thread show
 * through.
 */
type Expr = string | { over: string; alpha: number; ground: string };
const APP_ROLES: Record<string, { light: Expr; dark: Expr }> = {
  /** What is chosen (a chip, a segment): ink, with a check, never colour alone. */
  selection: { light: "var(--color-rich-black)", dark: "var(--color-anti-flash)" },
  onSelection: { light: "var(--color-anti-flash)", dark: "var(--color-ink-surface)" },
  /** What deserves attention (unread dot, «hoy», the calm card): the brand's mint. */
  highlight: { light: "var(--color-mountain-meadow)", dark: "var(--color-mountain-meadow)" },
  highlightSoft: {
    light: "color-mix(in oklab, var(--color-mountain-meadow) 16%, transparent)",
    dark: "color-mix(in oklab, var(--color-mountain-meadow) 16%, transparent)",
  },
  onHighlight: { light: "var(--color-dark-green)", dark: "var(--color-dark-green)" },
  /** Small text in the highlight's hue that still reads at 4.5:1 on the ground (basil, not the demo's #087F5C). */
  highlightInk: { light: "var(--color-basil)", dark: "var(--color-mountain-meadow)" },
  /**
   * The edge of a control (a chip, a free hour, a block, the chosen segment):
   * the ink at half, 3:1 or more on a card, the screen and a muted track (R3.5).
   * `border` stays for dividers and cards, which are not controls.
   */
  controlBorder: {
    light: "color-mix(in oklab, var(--foreground) 50%, transparent)",
    dark: "color-mix(in oklab, var(--foreground) 50%, transparent)",
  },
  /** The agent's bubble: the mint at 16 % over the card, made opaque. */
  bubbleAgent: {
    light: { over: "var(--color-mountain-meadow)", alpha: 0.16, ground: "var(--card)" },
    dark: { over: "var(--color-mountain-meadow)", alpha: 0.16, ground: "var(--card)" },
  },
  /** The toast is the inverse of the screen: dark on a light screen, light on a dark one. */
  toastBg: { light: "var(--foreground)", dark: "var(--foreground)" },
  toastFg: { light: "var(--background)", dark: "var(--background)" },
  toastAccent: { light: "var(--color-mountain-meadow)", dark: "var(--color-bangladesh-green)" },
};

/**
 * The channels' own colours (the logos of WhatsApp, Instagram and Messenger),
 * lighter in dark so they keep their contrast. Brand marks, not theme roles:
 * they live here so no screen writes a hex.
 */
const GOOGLE = { googleRed: "#EA4335", googleBlue: "#4285F4", googleYellow: "#FBBC05", googleGreen: "#34A853" };
const BRAND = {
  light: { whatsapp: "#1FA855", instagram: "#D6336C", messenger: "#0A7CFF", onBrand: "#FFFFFF", ...GOOGLE },
  dark: { whatsapp: "#25D366", instagram: "#F06595", messenger: "#4DA3FF", onBrand: "#FFFFFF", ...GOOGLE },
} as const;

function overHex(fg: string, alpha: number, ground: string): string {
  const a = gamut(color(fg));
  const b = gamut(color(ground));
  const mix = (x: number | undefined, y: number | undefined) => (x ?? 0) * alpha + (y ?? 0) * (1 - alpha);
  return formatHex({ mode: "rgb", r: mix(a.r, b.r), g: mix(a.g, b.g), b: mix(a.b, b.b) } as Color).toUpperCase();
}

function appPalette(vars: Record<string, string>, scheme: "light" | "dark"): Record<string, string> {
  return Object.fromEntries(
    Object.entries(APP_ROLES).map(([role, by]) => {
      const e = by[scheme];
      if (typeof e === "string") return [role, hex(resolve(e, vars))];
      return [role, overHex(resolve(e.over, vars), e.alpha, resolve(e.ground, vars))];
    }),
  );
}

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
  light: { ...palette(light), ...appPalette(light, "light") },
  dark: { ...palette(dark), ...appPalette(dark, "dark") },
  brand: BRAND,
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
