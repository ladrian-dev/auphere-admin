/**
 * @nexus/ui ESLint plugin — the lint that keeps the design system honest
 * (PLAN-CONSOLE-V1 CP-01 acceptance: "un lint falla si aparece un hex en
 * JSX o un valor de espaciado fuera de escala").
 *
 * Rules (all errors under the recommended config):
 *
 *   nexus-ui/no-raw-colors     — no `#hex`, `rgb(`, `hsl(`, `oklch(` in
 *                                 TS/TSX/JS string literals, template literals
 *                                 or JSX attributes. Colour is a token.
 *   nexus-ui/spacing-scale     — Tailwind spacing/sizing utilities stay on
 *                                 the 4 px grid: integer steps only (no
 *                                 `gap-1.5`), arbitrary `[Npx]` multiples of 4.
 *   nexus-ui/radius-enum       — `rounded-*` ∈ {none, sm, md, full}.
 *   nexus-ui/no-palette-colors — no `text-slate-500`, `bg-zinc-100`, … the
 *                                 default Tailwind palette is not the brand.
 *
 * Plain JS (no build step) so both this package and apps/console load it
 * straight from `@nexus/ui/eslint`.
 */

const HEX_RE = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/;
const FN_RE = /\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(/;

// Utilities whose value is a length on the spacing scale.
const SPACING_PREFIXES = [
  "p", "px", "py", "pt", "pr", "pb", "pl", "ps", "pe",
  "m", "mx", "my", "mt", "mr", "mb", "ml", "ms", "me",
  "gap", "gap-x", "gap-y", "space-x", "space-y",
  "inset", "inset-x", "inset-y", "top", "right", "bottom", "left", "start", "end",
  "w", "h", "size", "min-w", "min-h", "max-w", "max-h", "basis",
  "translate-x", "translate-y", "scroll-m", "scroll-p", "indent",
];
const SPACING_RE = new RegExp(
  `^(?:[a-z0-9-]+:)*-?(?:${SPACING_PREFIXES.map((p) => p.replace(/-/g, "\\-")).join("|")})-(.+)$`,
);
const ALLOWED_WORDS = new Set([
  "px", "auto", "full", "screen", "fit", "min", "max", "prose", "none", "svh", "lvh", "dvh",
  "svw", "lvw", "dvw", "3xs", "2xs", "xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl",
  "6xl", "7xl",
]);

const PALETTE_RE =
  /\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|decoration|accent|caret|shadow|divide|placeholder)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|[1-9]00|950)\b/;

const RADIUS_RE = /(?:^|[\s"'`:])((?:[a-z0-9-]+:)*rounded(?:-(?:t|b|l|r|s|e|tl|tr|bl|br|ss|se|es|ee))?(?:-([a-z0-9[\]]+))?)(?=[\s"'`]|$)/g;
const RADIUS_OK = new Set([undefined, "none", "sm", "md", "full"]);

function classTokens(text) {
  return text.split(/\s+/).filter(Boolean);
}

function checkSpacingToken(token) {
  const m = SPACING_RE.exec(token);
  if (!m) return null;
  const value = m[1];
  if (ALLOWED_WORDS.has(value)) return null;
  if (/^\d+\/\d+$/.test(value)) return null; // fractions
  if (/^\(--[a-z0-9-]+\)$/.test(value)) return null; // (--var)
  if (/^\[.+\]$/.test(value)) {
    const inner = value.slice(1, -1);
    const px = /^(-?\d+(?:\.\d+)?)px$/.exec(inner);
    if (px) {
      const n = Number(px[1]);
      return Number.isInteger(n) && n % 4 === 0 ? null : `arbitrary ${inner} is off the 4 px grid`;
    }
    if (/^(?:calc|var|min|max|clamp)\(/.test(inner) || /%$/.test(inner)) return null;
    if (/^-?\d+(?:\.\d+)?(?:rem|em|vh|vw|ch)$/.test(inner)) return null;
    return null;
  }
  if (/^\d+(?:\.\d+)?$/.test(value)) {
    return Number.isInteger(Number(value)) ? null : `${value} is a half-step (${Number(value) * 4} px)`;
  }
  return null;
}

function forEachStringNode(context, callback) {
  return {
    Literal(node) {
      if (typeof node.value === "string") callback(node, node.value);
    },
    TemplateElement(node) {
      callback(node, node.value.cooked ?? node.value.raw ?? "");
    },
  };
}

const noRawColors = {
  meta: {
    type: "problem",
    docs: { description: "Colour must come from a design token, never a literal." },
    schema: [],
    messages: {
      raw: "Raw colour \"{{ value }}\" in code. Use a token (bg-primary, text-status-danger, var(--color-…)).",
    },
  },
  create(context) {
    return forEachStringNode(context, (node, value) => {
      if (HEX_RE.test(value) || FN_RE.test(value)) {
        // Allow CSS var references that merely CONTAIN a colour function
        // name inside color-mix(in oklab, var(--…) …): the operands are vars.
        const stripped = value.replace(/color-mix\([^)]*\)/g, "").replace(/var\(--[a-z0-9-]+\)/g, "");
        if (HEX_RE.test(stripped) || FN_RE.test(stripped)) {
          context.report({ node, messageId: "raw", data: { value: value.slice(0, 40) } });
        }
      }
    });
  },
};

const spacingScale = {
  meta: {
    type: "problem",
    docs: { description: "Spacing/sizing utilities stay on the 4 px grid." },
    schema: [],
    messages: { off: "\"{{ token }}\": {{ why }}. Use a multiple of 4 px." },
  },
  create(context) {
    return forEachStringNode(context, (node, value) => {
      for (const token of classTokens(value)) {
        const why = checkSpacingToken(token);
        if (why) context.report({ node, messageId: "off", data: { token, why } });
      }
    });
  },
};

const radiusEnum = {
  meta: {
    type: "problem",
    docs: { description: "Radius is an enum: rounded-none | rounded-sm | rounded-md | rounded-full." },
    schema: [],
    messages: { off: "\"{{ token }}\" is outside the radius enum {none, sm(4), md(8), full}." },
  },
  create(context) {
    return forEachStringNode(context, (node, value) => {
      for (const token of classTokens(value)) {
        const m = /^(?:[a-z0-9-]+:)*rounded(?:-(?:t|b|l|r|s|e|tl|tr|bl|br|ss|se|es|ee))?(?:-([a-z0-9[\]().-]+))?$/.exec(token);
        if (!m) continue;
        const v = m[1];
        if (RADIUS_OK.has(v)) continue;
        if (v && /^\(--[a-z0-9-]+\)$/.test(v)) continue;
        context.report({ node, messageId: "off", data: { token } });
      }
    });
  },
};

const noPaletteColors = {
  meta: {
    type: "problem",
    docs: { description: "The default Tailwind palette is not the brand — use semantic tokens." },
    schema: [],
    messages: { off: "\"{{ token }}\" uses the default palette. Use bg-muted / text-muted-foreground / status tokens." },
  },
  create(context) {
    return forEachStringNode(context, (node, value) => {
      for (const token of classTokens(value)) {
        if (PALETTE_RE.test(token)) context.report({ node, messageId: "off", data: { token } });
      }
    });
  },
};

const plugin = {
  meta: { name: "@nexus/ui-eslint", version: "0.1.0" },
  rules: {
    "no-raw-colors": noRawColors,
    "spacing-scale": spacingScale,
    "radius-enum": radiusEnum,
    "no-palette-colors": noPaletteColors,
  },
  configs: {},
};

plugin.configs.recommended = {
  name: "nexus-ui/recommended",
  plugins: { "nexus-ui": plugin },
  files: ["**/*.{ts,tsx,js,jsx,mts,mjs}"],
  ignores: ["**/*.css", "**/dist/**", "**/.next/**", "**/storybook-static/**"],
  rules: {
    "nexus-ui/no-raw-colors": "error",
    "nexus-ui/spacing-scale": "error",
    "nexus-ui/radius-enum": "error",
    "nexus-ui/no-palette-colors": "error",
  },
};

export default plugin;
export { RADIUS_RE, checkSpacingToken, HEX_RE, FN_RE, PALETTE_RE };
