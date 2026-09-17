/**
 * Contraste — spec 010, Requisito 2.4.
 *
 * Lo justo para poder **comprobar** los tokens en un test en vez de confiar en
 * que alguien los mire: convertir OKLCH (que es como está escrita la paleta) a
 * sRGB, componer lo translúcido sobre su fondo, y calcular la razón de
 * contraste de WCAG 2.2.
 *
 * No es una librería de color: no hay gamut mapping ni espacios anchos. Es lo
 * necesario para responder a una pregunta binaria — ¿este par pasa el umbral?—,
 * y esa pregunta es la que impide que el sistema visual se degrade sin que
 * nadie se entere.
 */

export type Rgb = { r: number; g: number; b: number };
export type Color = { rgb: Rgb; alpha: number };

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/** OKLab → sRGB lineal → sRGB (0-1), según la conversión de la especificación CSS Color 4. */
function oklchToRgb(l: number, c: number, hDeg: number): Rgb {
  const h = (hDeg * Math.PI) / 180;
  const a = c * Math.cos(h);
  const bb = c * Math.sin(h);

  const l_ = l + 0.3963377774 * a + 0.2158037573 * bb;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * bb;
  const s_ = l - 0.0894841775 * a - 1.291485548 * bb;

  const L = l_ ** 3;
  const M = m_ ** 3;
  const S = s_ ** 3;

  const lr = 4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S;
  const lg = -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S;
  const lb = -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S;

  const gamma = (u: number): number => {
    const v = clamp01(u);
    return v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
  };

  return { r: gamma(lr), g: gamma(lg), b: gamma(lb) };
}

/**
 * Lee un color de la paleta. Admite `oklch(L C H)`, `oklch(L C H / a)` y
 * `#rrggbb`, que es todo lo que aparece en `tokens.css`.
 */
export function parseColor(value: string): Color | null {
  const text = value.trim();

  const oklch = text.match(/^oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/i);
  if (oklch) {
    const [, rawL = "0", rawC = "0", rawH = "0", rawA] = oklch;
    const l = rawL.endsWith("%") ? Number.parseFloat(rawL) / 100 : Number.parseFloat(rawL);
    const alpha = rawA === undefined ? 1 : rawA.endsWith("%") ? Number.parseFloat(rawA) / 100 : Number.parseFloat(rawA);
    return { rgb: oklchToRgb(l, Number.parseFloat(rawC), Number.parseFloat(rawH)), alpha };
  }

  const hex = text.match(/^#([0-9a-f]{6})$/i);
  if (hex?.[1]) {
    const n = Number.parseInt(hex[1], 16);
    return { rgb: { r: ((n >> 16) & 255) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255 }, alpha: 1 };
  }

  return null;
}

/** Lo translúcido se ve sobre algo: se compone antes de medir. */
export function over(top: Color, bottom: Rgb): Rgb {
  const mix = (a: number, b: number): number => a * top.alpha + b * (1 - top.alpha);
  return { r: mix(top.rgb.r, bottom.r), g: mix(top.rgb.g, bottom.g), b: mix(top.rgb.b, bottom.b) };
}

/** Luminancia relativa (WCAG 2.2). */
export function luminance(rgb: Rgb): number {
  const channel = (u: number): number => {
    const v = clamp01(u);
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
}

/** La razón de contraste entre dos colores ya compuestos. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [light, dark] = la > lb ? [la, lb] : [lb, la];
  return ((light as number) + 0.05) / ((dark as number) + 0.05);
}

/** El contraste de un color (quizá translúcido) sobre un fondo opaco. */
export function ratioOn(foreground: Color, background: Color): number {
  const bg = over({ ...background, alpha: 1 }, { r: 1, g: 1, b: 1 });
  return contrastRatio(over(foreground, bg), bg);
}
